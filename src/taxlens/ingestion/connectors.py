from __future__ import annotations

import hashlib
import html as html_module
import logging
import re
import time
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, TypedDict
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from taxlens.document_processing.formats import detect_format
from taxlens.legal_data.document_numbers import (
    DOCUMENT_NUMBER_PATTERN,
    issuer_code,
    issuing_agency_for,
    normalize_number_text,
)

logger = logging.getLogger(__name__)


class ConnectorError(RuntimeError):
    """Raised when an official source cannot be safely fetched."""


@dataclass(frozen=True)
class SourceDocument:
    source_name: str
    source_document_id: str
    document_number: str
    title: str
    source_url: str
    content_url: str
    content_type: str = "application/pdf"
    document_type: str = "official_pdf"
    issuing_agency: str | None = None
    issue_date: date | None = None
    legal_status: str = "DISCOVERED"
    effective_date: date | None = None


class SourceConnector(Protocol):
    source_name: str

    def list_documents(self, since: date | None = None) -> list[SourceDocument]: ...

    def fetch_document(self, document: SourceDocument) -> bytes: ...

    def fetch_metadata(self, document: SourceDocument) -> dict[str, str]: ...


class OfficialPortalConnector:
    def __init__(
        self,
        source_name: str,
        catalog_url: str,
        allowed_host: str | tuple[str, ...],
        client: httpx.Client | None = None,
        user_agent: str = "TaxLens-AI/0.1 (+https://github.com/taxlens-ai)",
        max_pages: int = 1,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        self.source_name = source_name
        self.catalog_url = catalog_url
        self.allowed_hosts = (allowed_host,) if isinstance(allowed_host, str) else allowed_host
        self.max_pages = max_pages
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )

    def list_documents(self, since: date | None = None) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        pending_urls = [self.catalog_url]
        visited_urls: set[str] = set()
        while pending_urls and len(visited_urls) < self.max_pages:
            catalog_url = pending_urls.pop(0)
            if catalog_url in visited_urls or not self._is_allowed(catalog_url):
                continue
            visited_urls.add(catalog_url)
            response = self._request("GET", catalog_url)
            page_documents, pagination_urls = self._parse_catalog_page(
                response.text, catalog_url, since
            )
            documents.extend(page_documents)
            for pagination_url in pagination_urls:
                if pagination_url not in visited_urls and pagination_url not in pending_urls:
                    pending_urls.append(pagination_url)
        return _deduplicate_documents(documents)

    def _parse_catalog_page(
        self, html: str, catalog_url: str, since: date | None
    ) -> tuple[list[SourceDocument], list[str]]:
        documents: list[SourceDocument] = []
        current_document_number: str | None = None
        current_title = ""
        current_source_url = catalog_url
        pagination_urls: list[str] = []
        row_documents = self._parse_result_rows(html, catalog_url, since)
        for href, raw_title, attributes in _extract_links(html):
            content_url = urljoin(catalog_url, href)
            if not self._is_allowed(content_url):
                continue
            if _is_pagination_link(href, raw_title, attributes):
                pagination_urls.append(content_url)
                continue
            if row_documents is not None:
                continue
            match = DOCUMENT_NUMBER_PATTERN.search(f"{content_url} {raw_title}".upper())
            is_attachment = (
                "tài liệu" in raw_title.casefold() or "attachment" in raw_title.casefold()
            )
            if match is not None:
                current_document_number = match.group(0)
                current_title = raw_title or current_document_number
                current_source_url = content_url
            elif not is_attachment:
                continue
            if not _is_pdf_url(content_url) or current_document_number is None:
                continue
            issue_date = _extract_issue_date(current_title)
            if since is not None and issue_date is not None and issue_date < since:
                continue
            document_number = current_document_number
            source_document_id = hashlib.sha256(content_url.encode()).hexdigest()[:24]
            documents.append(
                SourceDocument(
                    source_name=self.source_name,
                    source_document_id=source_document_id,
                    document_number=document_number,
                    title=current_title or document_number,
                    source_url=current_source_url,
                    content_url=content_url,
                    document_type=_document_type(document_number),
                    # Portals republish documents from many issuers; the number identifies it.
                    issuing_agency=issuing_agency_for(document_number)
                    or _ISSUING_AGENCIES.get(self.source_name),
                    issue_date=issue_date,
                )
            )
        if row_documents is not None:
            return row_documents, pagination_urls
        return documents, pagination_urls

    def _parse_result_rows(
        self, html: str, catalog_url: str, since: date | None
    ) -> list[SourceDocument] | None:
        """Parse result tables that mark each document's own number (vanban.chinhphu.vn).

        Link-order scanning is wrong for these rows: the summary of an amending document
        cites the document it amends ("Sửa đổi ... Nghị định số 112/2017/NĐ-CP"), which
        would replace the row's own number before its PDF link is reached.
        Returns None when the page has no such rows.
        """

        rows = [row for row in _ROW_PATTERN.findall(html) if _CODE_SPAN_PATTERN.search(row)]
        if not rows:
            return None
        documents: list[SourceDocument] = []
        for row in rows:
            code_match = _CODE_SPAN_PATTERN.search(row)
            if code_match is None:
                continue
            code = normalize_number_text(_html_text(code_match.group(1))).upper()
            number_match = DOCUMENT_NUMBER_PATTERN.search(code)
            if number_match is not None:
                document_number = number_match.group(0)
            elif re.match(r"^\d+\s*[/-]", code):
                # Older numbering ("28-CP", "94-TC/TCT") predates the modern pattern; the
                # row's own number field is still authoritative.
                document_number = " ".join(code.split())
            else:
                continue
            summary_match = _SUMMARY_SPAN_PATTERN.search(row)
            title = _html_text(summary_match.group(1)) if summary_match else document_number
            date_match = _ISSUED_DATE_SPAN_PATTERN.search(row)
            issue_date = (
                _extract_issue_date(_html_text(date_match.group(1))) if date_match else None
            )
            if since is not None and issue_date is not None and issue_date < since:
                continue
            links = [urljoin(catalog_url, href) for href, _, _ in _extract_links(row)]
            allowed_links = [link for link in links if self._is_allowed(link)]
            detail_url = next(
                (link for link in allowed_links if _file_extension(link) is None), catalog_url
            )
            # One file per document: a Word file has exact text, a PDF usually needs OCR,
            # and further PDFs are appendices (forms) that cost OCR time for little value.
            content_url = _preferred_file(allowed_links)
            if content_url is None:
                continue
            documents.append(
                SourceDocument(
                    source_name=self.source_name,
                    source_document_id=hashlib.sha256(content_url.encode()).hexdigest()[:24],
                    document_number=document_number,
                    title=title or document_number,
                    source_url=detail_url,
                    content_url=content_url,
                    content_type=_content_type_for(content_url),
                    document_type=_document_type(document_number),
                    issuing_agency=issuing_agency_for(document_number)
                    or _ISSUING_AGENCIES.get(self.source_name),
                    issue_date=issue_date,
                )
            )
        return documents

    def fetch_document(self, document: SourceDocument) -> bytes:
        self._validate_url(document.content_url)
        response = self._request("GET", document.content_url)
        content = response.content
        if detect_format(content) == "text":
            # An HTML error page or an unsupported file, not a document.
            raise ConnectorError(f"Expected a PDF or Word document: {document.content_url}")
        return content

    def fetch_metadata(self, document: SourceDocument) -> dict[str, str]:
        self._validate_url(document.content_url)
        response = self._request("HEAD", document.content_url)
        return {
            "source_name": document.source_name,
            "source_url": document.source_url,
            "content_url": document.content_url,
            "document_number": document.document_number,
            "title": document.title,
            "content_type": response.headers.get("content-type", ""),
            "content_length": response.headers.get("content-length", ""),
        }

    def _request(self, method: str, url: str) -> httpx.Response:
        self._validate_url(url)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.request(method, url)
                response.raise_for_status()
                return response
            except httpx.HTTPError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.25 * (attempt + 1))
        raise ConnectorError(f"Source request failed: {url}") from last_error

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise ConnectorError(f"URL is outside the allowed official host: {url}")

    def _is_allowed(self, url: str) -> bool:
        try:
            self._validate_url(url)
        except ConnectorError:
            return False
        return True


class OfficialSourceConfig(TypedDict):
    source_name: str
    catalog_url: str
    allowed_host: str | tuple[str, ...]
    max_pages: int


OFFICIAL_SOURCE_CATALOGS: dict[str, OfficialSourceConfig] = {
    "mof": {
        "source_name": "mof-vbpq",
        "catalog_url": "https://vbpq.mof.gov.vn/",
        "allowed_host": "vbpq.mof.gov.vn",
        "max_pages": 5,
    },
    "government": {
        "source_name": "government-portal",
        "catalog_url": "https://vanban.chinhphu.vn/he-thong-van-ban?classid=1",
        "allowed_host": ("vanban.chinhphu.vn", "datafiles.chinhphu.vn"),
        "max_pages": 10,
    },
}


def create_official_connector(
    source: str,
    client: httpx.Client | None = None,
    max_pages: int | None = None,
) -> OfficialPortalConnector:
    try:
        config = OFFICIAL_SOURCE_CATALOGS[source]
    except KeyError as error:
        raise ConnectorError(f"Unknown official source: {source}") from error
    return OfficialPortalConnector(
        source_name=config["source_name"],
        catalog_url=config["catalog_url"],
        allowed_host=config["allowed_host"],
        max_pages=max_pages if max_pages is not None else config["max_pages"],
        client=client,
    )


_DATE_PATTERN = re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b")
_ROW_PATTERN = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)


def _span_pattern(css_class: str) -> re.Pattern[str]:
    return re.compile(
        rf"<span\b[^>]*class=[\"'][^\"']*\b{css_class}\b[^\"']*[\"'][^>]*>(.*?)</span>",
        re.IGNORECASE | re.DOTALL,
    )


_CODE_SPAN_PATTERN = _span_pattern("code")
_SUMMARY_SPAN_PATTERN = _span_pattern("substract")
_ISSUED_DATE_SPAN_PATTERN = _span_pattern("issued-date")


def _html_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html_module.unescape(text).split())
_ISSUING_AGENCIES = {
    "government-portal": "Government of Vietnam",
    "mof-vbpq": "Ministry of Finance",
}
# Whole-word topic terms for the tax corpus; whole words avoid "phí" matching "phía".
_TAX_TOPIC_PATTERN = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(term)
        for term in (
            "thuế",
            "hóa đơn",
            "hoá đơn",
            "chứng từ",
            # Fees and charges; bare "phí" would also match "kinh phí" and "chi phí".
            "lệ phí",
            "thu phí",
            "kế toán",
            # Financial audit only; "kiểm toán năng lượng" is an energy audit.
            "kiểm toán độc lập",
            "kiểm toán viên",
            "chuẩn mực kiểm toán",
            "hải quan",
            "tax",
            "invoice",
        )
    )
    + r")(?!\w)"
)
# Issuers whose documents are presumed relevant when a listing shows no summary to judge.
_TAX_ISSUER_CODES = frozenset({"BTC", "TCT", "TCHQ"})


def is_tax_relevant(document: SourceDocument) -> bool:
    """Whether a discovered document belongs in the tax corpus.

    The government portal lists every legal document (health standards, children's
    forums, ...), so discovery keeps only titles about tax, invoices, fees, accounting, or
    customs. Titles without a summary fall back to the issuing body.
    """

    return is_tax_title(document.title, document.document_number)


def is_tax_title(title: str, document_number: str) -> bool:
    """The tax-relevance rule of ``is_tax_relevant`` for a stored title and number."""

    normalized = unicodedata.normalize("NFC", title).casefold()
    summary = normalized.replace(document_number.casefold(), " ")
    if _TAX_TOPIC_PATTERN.search(summary):
        return True
    if len(re.findall(r"[^\W\d_]{2,}", summary)) < 3:
        return issuer_code(document_number) in _TAX_ISSUER_CODES
    return False


def _extract_links(html: str) -> Iterator[tuple[str, str, str]]:
    for match in re.finditer(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = re.sub(r"<[^>]+>", " ", match.group(2))
        yield match.group(1), " ".join(title.split()), match.group(0)


def _is_pagination_link(href: str, title: str, attributes: str) -> bool:
    normalized_title = title.casefold().strip()
    if "rel=\"next\"" in attributes.casefold() or "rel='next'" in attributes.casefold():
        return True
    if normalized_title in {"next", "sau", ">", "›", "»"}:
        return True
    query = parse_qs(urlparse(href).query)
    pagination_keys = {"page", "pageindex", "p", "trang"}
    return any(key.casefold() in pagination_keys for key in query)


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


_FILE_PREFERENCE = (".docx", ".doc", ".rtf", ".pdf")
_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".rtf": "application/rtf",
    ".pdf": "application/pdf",
}


def _file_extension(url: str) -> str | None:
    path = urlparse(url).path.lower()
    return next((extension for extension in _FILE_PREFERENCE if path.endswith(extension)), None)


def _preferred_file(urls: list[str]) -> str | None:
    files = [url for url in urls if _file_extension(url) is not None]
    if not files:
        return None
    return min(files, key=lambda url: _FILE_PREFERENCE.index(_file_extension(url) or ".pdf"))


def _content_type_for(url: str) -> str:
    return _CONTENT_TYPES.get(_file_extension(url) or ".pdf", "application/pdf")


def _document_type(document_number: str) -> str:
    return document_number.rsplit("/", 1)[-1].upper()


def _extract_issue_date(title: str) -> date | None:
    match = _DATE_PATTERN.search(title)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(0).replace("/", "-"), "%d-%m-%Y").date()
    except ValueError:
        return None


def _deduplicate_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    unique: dict[str, SourceDocument] = {}
    for document in documents:
        unique.setdefault(document.content_url, document)
    return list(unique.values())


GOVERNMENT_SEARCH_URL = "https://vanban.chinhphu.vn/he-thong-van-ban?classid=1"
TAX_CATEGORY_ID = "29"  # "Thuế - Lệ phí"
# National issuers, used to split a year whose search hits the result cap.
NATIONAL_ISSUER_IDS = ("1", "163", "690", "2", "3", "169", "166", "8", "149")
# Provincial people's committees and councils issue local fee rules, outside the corpus.
LOCAL_ISSUER_CODES = frozenset({"UBND", "HĐND", "UB"})
SEARCH_RESULT_CAP = 50
_FORM_PREFIX = "ctrl_191017_163$"


class GovernmentPortalSearch:
    """Search the government portal's tax category year by year (vanban.chinhphu.vn).

    The listing pages only reach the newest documents (pagination is an ASP.NET
    post-back), but the search form filters by category, year, and issuer. A search shows
    at most 50 results without usable paging, so a year that hits the cap is searched again
    per national issuer.
    """

    source_name = "government-portal"

    def __init__(self, client: httpx.Client | None = None, delay_seconds: float = 1.0) -> None:
        self._portal = create_official_connector("government", client=client)
        self._client = self._portal._client
        self._delay_seconds = delay_seconds
        self._blank_form: dict[str, str] | None = None

    def tax_documents(self, years: Iterable[int]) -> list[SourceDocument]:
        documents: dict[str, SourceDocument] = {}
        for year in years:
            found, capped = self._search(year)
            if capped:
                for issuer in NATIONAL_ISSUER_IDS:
                    found.extend(self._search(year, issuer)[0])
            logger.info(
                "Government portal %d: %d result(s)%s",
                year,
                len(found),
                " (capped; searched per national issuer)" if capped else "",
            )
            for document in found:
                if issuer_code(document.document_number) not in LOCAL_ISSUER_CODES:
                    documents.setdefault(document.content_url, document)
        return list(documents.values())

    def fetch_document(self, document: SourceDocument) -> bytes:
        return self._portal.fetch_document(document)

    def _search(self, year: int, issuer: str | None = None) -> tuple[list[SourceDocument], bool]:
        form = dict(self._form())
        form.update(
            {
                f"{_FORM_PREFIX}drdDocCategory": TAX_CATEGORY_ID,
                f"{_FORM_PREFIX}drdDocYear": str(year),
                f"{_FORM_PREFIX}drdDocOrg": issuer or "0",
                f"{_FORM_PREFIX}btnSearch": "Tìm kiếm",
            }
        )
        time.sleep(self._delay_seconds)
        response = self._client.post(GOVERNMENT_SEARCH_URL, data=form)
        response.raise_for_status()
        page = response.text
        rows = self._portal._parse_result_rows(page, GOVERNMENT_SEARCH_URL, None) or []
        return rows, len(_CODE_SPAN_PATTERN.findall(page)) >= SEARCH_RESULT_CAP

    def _form(self) -> dict[str, str]:
        if self._blank_form is None:
            response = self._client.get(GOVERNMENT_SEARCH_URL)
            response.raise_for_status()
            self._blank_form = _form_fields(response.text)
        return self._blank_form


def _form_fields(page: str) -> dict[str, str]:
    """The current values of an ASP.NET form, including its view state."""

    fields: dict[str, str] = {}
    for match in re.finditer(r"<input\b[^>]*>", page):
        tag = match.group(0)
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        kind = re.search(r'type="([^"]+)"', tag)
        if kind and kind.group(1) in ("submit", "button", "image"):
            continue
        value = re.search(r'value="([^"]*)"', tag)
        fields[html_module.unescape(name.group(1))] = (
            html_module.unescape(value.group(1)) if value else ""
        )
    for match in re.finditer(r'<select\b[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        selected = re.search(r'<option[^>]*selected="selected"[^>]*value="([^"]*)"', match.group(2))
        first = re.search(r'<option[^>]*value="([^"]*)"', match.group(2))
        option = selected or first
        fields[html_module.unescape(match.group(1))] = option.group(1) if option else ""
    return fields
