import httpx
import pytest

from taxlens.ingestion.connectors import (
    ConnectorError,
    OfficialPortalConnector,
    SourceDocument,
    create_official_connector,
)


def test_official_connector_discovers_pdf_documents_and_deduplicates_links() -> None:
    html = (
        '<a href="/files/31/2025/TT-BTC.pdf">31/2025/TT-BTC guidance</a>'
        '<a href="/files/31/2025/TT-BTC.pdf">duplicate</a>'
        '<a href="https://example.com/02/2024/TT-BTC.pdf">outside</a>'
        '<a href="/files/not-a-document.pdf">missing number</a>'
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html))
    )
    connector = OfficialPortalConnector(
        source_name="test-source",
        catalog_url="https://vbpq.mof.gov.vn/",
        allowed_host="vbpq.mof.gov.vn",
        client=client,
    )

    documents = connector.list_documents()

    assert len(documents) == 1
    assert documents[0].document_number == "31/2025/TT-BTC"
    assert documents[0].title == "31/2025/TT-BTC guidance"


def test_official_connector_follows_bounded_catalog_pagination() -> None:
    pages = {
        "https://government.test/catalog": (
            '<a href="/catalog?page=2">2</a>'
            '<a href="/files/31/2025/TT-BTC.pdf">31/2025/TT-BTC first</a>'
        ),
        "https://government.test/catalog?page=2": (
            '<a href="/files/02/2025/TT-BTC.pdf">02/2025/TT-BTC second</a>'
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pages[ str(request.url) ])

    connector = OfficialPortalConnector(
        source_name="test-source",
        catalog_url="https://government.test/catalog",
        allowed_host="government.test",
        max_pages=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    documents = connector.list_documents()

    assert [document.document_number for document in documents] == [
        "31/2025/TT-BTC",
        "02/2025/TT-BTC",
    ]


def test_official_connector_extracts_basic_document_metadata() -> None:
    html = '<a href="/files/304/2026/304_2026_nd-cp.pdf">304/2026/NĐ-CP 03/08/2026</a>'
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html))
    )
    connector = OfficialPortalConnector(
        source_name="government-portal",
        catalog_url="https://vanban.chinhphu.vn/he-thong-van-ban?classid=1",
        allowed_host=("vanban.chinhphu.vn", "datafiles.chinhphu.vn"),
        client=client,
    )

    document = connector.list_documents()[0]

    assert document.document_type == "NĐ-CP"
    assert document.issuing_agency == "Government of Vietnam"
    assert document.issue_date.isoformat() == "2026-08-03"


def test_official_connector_fetches_pdf_and_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf", "content-length": "4"},
            )
        return httpx.Response(200, content=b"%PDF-test")

    connector = OfficialPortalConnector(
        source_name="test-source",
        catalog_url="https://vbpq.mof.gov.vn/",
        allowed_host="vbpq.mof.gov.vn",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    document = SourceDocument(
        source_name="test-source",
        source_document_id="abc",
        document_number="31/2025/TT-BTC",
        title="Test document",
        source_url="https://vbpq.mof.gov.vn/",
        content_url="https://vbpq.mof.gov.vn/files/31/2025/TT-BTC.pdf",
    )

    assert connector.fetch_document(document).startswith(b"%PDF")
    assert connector.fetch_metadata(document)["content_type"] == "application/pdf"


def test_official_connector_rejects_non_pdf_and_unsafe_urls() -> None:
    connector = create_official_connector("mof")
    document = SourceDocument(
        source_name="mof-vbpq",
        source_document_id="abc",
        document_number="31/2025/TT-BTC",
        title="Test document",
        source_url="https://vbpq.mof.gov.vn/",
        content_url="http://vbpq.mof.gov.vn/file.pdf",
    )

    with pytest.raises(ConnectorError, match="allowed official host"):
        connector.fetch_document(document)
