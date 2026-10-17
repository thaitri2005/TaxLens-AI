from __future__ import annotations

import hashlib
import html as html_module
import re
import time
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, TypedDict
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from taxlens.legal_data.document_numbers import (
    DOCUMENT_NUMBER_PATTERN,
    issuer_code,
    issuing_agency_for,
)


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
            number_match = (
                DOCUMENT_NUMBER_PATTERN.search(_html_text(code_match.group(1)).upper())
                if code_match
                else None
            )
            if number_match is None:
                continue
            document_number = number_match.group(0)
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
                (link for link in allowed_links if not _is_pdf_url(link)), catalog_url
            )
            for content_url in allowed_links:
                if not _is_pdf_url(content_url):
                    continue
                documents.append(
                    SourceDocument(
                        source_name=self.source_name,
                        source_document_id=hashlib.sha256(content_url.encode()).hexdigest()[:24],
                        document_number=document_number,
                        title=title or document_number,
                        source_url=detail_url,
                        content_url=content_url,
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
        if not content.startswith(b"%PDF"):
            raise ConnectorError(f"Expected a PDF document: {document.content_url}")
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

    title = unicodedata.normalize("NFC", document.title).casefold()
    summary = title.replace(document.document_number.casefold(), " ")
    if _TAX_TOPIC_PATTERN.search(summary):
        return True
    if len(re.findall(r"[^\W\d_]{2,}", summary)) < 3:
        return issuer_code(document.document_number) in _TAX_ISSUER_CODES
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
