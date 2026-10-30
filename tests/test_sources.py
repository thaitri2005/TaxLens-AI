import json
import uuid
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from taxlens.document_processing.formats import detect_format, extract_word_processor_text
from taxlens.document_processing.legacy_text import convert_tcvn3
from taxlens.document_processing.process import build_article_chunks, find_section_headings
from taxlens.ingestion.connectors import ConnectorError, GovernmentPortalSearch, SourceDocument
from taxlens.ingestion.mof import MofLegalDocumentConnector, MofSearchOptions
from taxlens.ingestion.seed import ingest_source_document, is_already_ingested
from taxlens.legal_data.document_numbers import find_document_numbers
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.search import SearchResult, deduplicate_passages
from taxlens.storage.local import LocalObjectStorage


def test_tcvn3_text_is_converted_to_unicode_and_unicode_lines_are_kept() -> None:
    legacy = "Th«ng t­ h­íng dÉn thuÕ gi¸ trÞ gia t¨ng\nTH«NG T¦ cña Bé Tµi chÝnh"
    converted = convert_tcvn3(legacy + "\nThông tư đã là Unicode")

    assert converted.split("\n") == [
        "Thông tư hướng dẫn thuế giá trị gia tăng",
        "THÔNG TƯ của Bộ Tài chính",
        "Thông tư đã là Unicode",
    ]


def test_rtf_uses_each_font_charset_and_unicode_escapes() -> None:
    rtf = (
        rb"{\rtf1\ansi\ansicpg1252\deff0{\fonttbl{\f0\fcharset0 Times New Roman;}"
        rb"{\f1\fcharset163 Times New Roman (Vietnamese);}}"
        rb"{\f1 N\'e3m 2003 \'d0i\'ea\'ecu}\par "
        rb"S\u7889\'3f: 236\par}"
    )

    text = extract_word_processor_text(rtf)

    assert detect_format(rtf) == "rtf"
    assert [line.strip() for line in text.split("\n") if line.strip()] == [
        "Năm 2003 Điều".replace("Điều", "Điếu"),
        "Số: 236",
    ]


def test_docx_paragraphs_are_extracted() -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Điều 1. Phạm vi</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Nội dung</w:t><w:tab/><w:t>tiếp</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )

    assert extract_word_processor_text(buffer.getvalue()) == "Điều 1. Phạm vi\nNội dung\ttiếp"


def test_documents_without_articles_are_chunked_by_section() -> None:
    text = (
        "THÔNG TƯ hướng dẫn thuế đối với nhà thầu nước ngoài\n"
        "I. ĐỐI TƯỢNG ÁP DỤNG\n1. Tổ chức nước ngoài.\n2. Cá nhân nước ngoài.\n"
        "II. ĐỐI TƯỢNG KHÔNG ÁP DỤNG\nCác trường hợp khác.\n"
        "IV. Danh mục không phải tiêu đề\n"
        "III. THỜI HẠN NỘP THUẾ\nTrong mười ngày.\n"
    )

    headings = [heading.title for heading in find_section_headings(text)]
    chunks = build_article_chunks(text)

    assert headings == [
        "I. ĐỐI TƯỢNG ÁP DỤNG",
        "II. ĐỐI TƯỢNG KHÔNG ÁP DỤNG",
        "III. THỜI HẠN NỘP THUẾ",
    ]
    assert {chunk.heading for chunk in chunks if chunk.heading} == set(headings)
    assert all(chunk.page_start is None for chunk in chunks)


def test_cyrillic_lookalike_letters_in_document_numbers_are_normalized() -> None:
    assert find_document_numbers("255/2026/NĐ-CР") == ("255/2026/NĐ-CP",)


def test_mof_connector_selects_tax_documents_with_status_and_preferred_files() -> None:
    records = [
        _mof_record(1, "111/2013/TT-BTC", "Thông tư", "Đang hiệu lực", ["pdf", "doc", "rar"]),
        _mof_record(2, "18/VBHN-BTC", "Nghị định", "Đang hiệu lực", ["pdf"], vbhn=True),
        _mof_record(3, "219/2013/TT-BTC", "Thông tư", "Hết hiệu lực", ["doc"]),
        _mof_record(4, "2958/QĐ-BTC", "Quyết định", "Đang hiệu lực", ["pdf"]),
        _mof_record(5, "12/2020/TT-BTC", "Thông tư", "Đang hiệu lực", ["xls"]),
    ]
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        # Every selection returns the same records; the connector must deduplicate.
        page = records if body["Page"] == 1 else []
        return httpx.Response(200, json={"documents": page, "totalItem": len(records)})

    connector = MofLegalDocumentConnector(
        client=httpx.Client(transport=httpx.MockTransport(handler)), delay_seconds=0
    )

    documents = connector.list_documents(MofSearchOptions(issued_from=date(2010, 1, 1)))

    assert [document.document_number for document in documents] == [
        "111/2013/TT-BTC",
        "18/VBHN-BTC (2025)",
    ]
    circular = documents[0]
    assert circular.legal_status == "EFFECTIVE"
    assert circular.content_type == "application/msword"
    assert circular.content_url.endswith("/File/1001")  # the .doc, not the PDF
    assert circular.effective_date == date(2014, 1, 1)
    assert requests[0]["IssuedDateFrom"] == "01/01/2010"
    assert len(requests) == 4


def test_government_search_splits_capped_years_by_issuer_and_drops_local_documents() -> None:
    posts: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=_portal_form())
        form = dict(httpx.QueryParams(request.content.decode()))
        posts.append(form)
        issuer = form["ctrl_191017_163$drdDocOrg"]
        if issuer == "0":
            rows = [_portal_row(f"{n}/2016/TT-BTC", "pdf") for n in range(1, 51)]
        elif issuer == "2":
            rows = [_portal_row("167/2016/NĐ-CP", "doc"), _portal_row("5/2016/QĐ-UBND", "pdf")]
        else:
            rows = []
        return httpx.Response(200, text=f"<table>{''.join(rows)}</table>")

    search = GovernmentPortalSearch(
        client=httpx.Client(transport=httpx.MockTransport(handler)), delay_seconds=0
    )

    documents = search.tax_documents([2016])
    numbers = {document.document_number for document in documents}

    assert "167/2016/NĐ-CP" in numbers and "5/2016/QĐ-UBND" not in numbers
    assert len(numbers) == 51
    assert posts[0]["ctrl_191017_163$drdDocCategory"] == "29"
    assert len(posts) == 1 + 9
    decree = next(d for d in documents if d.document_number == "167/2016/NĐ-CP")
    assert decree.content_type == "application/msword"


def test_government_find_searches_every_category_by_keyword() -> None:
    posts: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=_portal_form())
        posts.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, text=f"<table>{_portal_row('31/2018/QH14', 'pdf')}</table>")

    search = GovernmentPortalSearch(
        client=httpx.Client(transport=httpx.MockTransport(handler)), delay_seconds=0
    )

    (document,) = search.find("31/2018/QH14")

    assert document.document_number == "31/2018/QH14"
    assert posts[0]["ctrl_191017_163$txtSearchKeyword"] == "31/2018/QH14"
    assert posts[0]["ctrl_191017_163$drdDocCategory"] == "0"
    assert posts[0]["ctrl_191017_163$drdDocYear"] == "0"


def test_government_search_retries_a_slow_year_and_skips_one_that_keeps_failing() -> None:
    attempts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=_portal_form())
        year = dict(httpx.QueryParams(request.content.decode()))["ctrl_191017_163$drdDocYear"]
        attempts[year] = attempts.get(year, 0) + 1
        if year == "2008" or (year == "2009" and attempts[year] == 1):
            raise httpx.ReadTimeout("slow portal", request=request)
        return httpx.Response(200, text=f"<table>{_portal_row(f'1/{year}/TT-BTC', 'pdf')}</table>")

    search = GovernmentPortalSearch(
        client=httpx.Client(transport=httpx.MockTransport(handler)), delay_seconds=0
    )

    documents = search.tax_documents([2009, 2008, 2007])

    assert {document.document_number for document in documents} == {
        "1/2009/TT-BTC",
        "1/2007/TT-BTC",
    }
    assert attempts == {"2009": 2, "2008": 3, "2007": 1}
    with pytest.raises(ConnectorError):
        search.tax_documents([2008])


def test_ingestion_records_source_status_and_improves_weak_titles(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalDocument.metadata.create_all(engine)
    storage = LocalObjectStorage(tmp_path)
    portal = _source("government-portal", "abc", "32/2025/TT-BTC 31/05/2025", "DISCOVERED")
    ministry = _source(
        "mof-vbpq", "585", "Hướng dẫn thực hiện một số điều của Luật Quản lý thuế", "EFFECTIVE"
    )
    with Session(engine) as session:
        ingest_source_document(session, storage, portal, b"%PDF portal copy")
        assert is_already_ingested(session, "government-portal", "abc")
        assert not is_already_ingested(session, "mof-vbpq", "585")
        ingest_source_document(session, storage, ministry, b"Word copy text")

        document = session.scalar(select(LegalDocument))
        statuses = set(session.scalars(select(DocumentVersion.legal_status)).all())

    assert document is not None
    assert document.title == "Hướng dẫn thực hiện một số điều của Luật Quản lý thuế"
    assert statuses == {"EFFECTIVE"}


def test_passages_repeated_in_another_version_are_removed() -> None:
    document = LegalDocument(id=uuid.uuid4(), document_number="1/2020/TT-BTC", title="T")
    first, second = (
        DocumentVersion(id=uuid.uuid4(), document_id=document.id, legal_status="EFFECTIVE")
        for _ in range(2)
    )

    def result(version: DocumentVersion, article: str, part: str) -> SearchResult:
        chunk = DocumentChunk(id=uuid.uuid4(), article_number=article, content=part)
        return SearchResult(chunk=chunk, version=version, document=document)

    results = [
        result(first, "5", "part one"),
        result(second, "5", "OCR copy"),
        result(first, "5", "part two"),
        result(second, "6", "other article"),
    ]

    assert [r.chunk.content for r in deduplicate_passages(results)] == [
        "part one",
        "part two",
        "other article",
    ]


def _mof_record(
    record_id: int,
    number: str,
    document_type: str,
    status: str,
    extensions: list[str],
    vbhn: bool = False,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "no": number,
        "contentType": "LegalDocument_VBHN" if vbhn else "LegalDocument",
        "documentTypeRecordName": document_type,
        "documentStatusRecordName": status,
        "summary": f"Văn bản {number}",
        "legalPublishDate": "2025-06-24T00:00:00",
        "legalApplyDate": "2014-01-01T00:00:00",
        "organizations": [{"name": "Bộ Tài chính", "id": 1}],
        "filePathCurrent": [
            {"id": record_id * 1000 + index, "inputFileName": f"file.{extension}"}
            for index, extension in enumerate(extensions)
        ],
    }


def _portal_form() -> str:
    return (
        '<form><input type="hidden" name="__VIEWSTATE" value="state" />'
        '<select name="ctrl_191017_163$drdDocCategory"><option value="0">All</option></select>'
        '<select name="ctrl_191017_163$drdDocYear"><option value="0">All</option></select>'
        '<select name="ctrl_191017_163$drdDocOrg"><option value="0">All</option></select>'
        "</form>"
    )


def _portal_row(number: str, extension: str) -> str:
    slug = number.replace("/", "-")
    links = f'<a href="https://datafiles.chinhphu.vn/files/{slug}.pdf">Tài liệu</a>'
    if extension == "doc":
        links += f'<a href="https://datafiles.chinhphu.vn/files/{slug}.doc">Tài liệu</a>'
    return (
        f"<tr><td><a href='/?docid={slug}'><span class=\"code\">{number}</span></a></td>"
        f'<td><span class="issued-date">01/06/2016</span></td>'
        f'<td><span class="substract">Quy định về thuế {number}</span>{links}</td></tr>'
    )


def _source(source: str, source_id: str, title: str, status: str) -> SourceDocument:
    return SourceDocument(
        source_name=source,
        source_document_id=source_id,
        document_number="32/2025/TT-BTC",
        title=title,
        source_url=f"https://example.invalid/{source}/{source_id}",
        content_url=f"https://example.invalid/{source}/{source_id}/file",
        legal_status=status,
        effective_date=date(2025, 6, 1) if status == "EFFECTIVE" else None,
    )
