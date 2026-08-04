from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Protocol, TypedDict
from urllib.parse import urljoin, urlparse

import httpx


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
    ) -> None:
        self.source_name = source_name
        self.catalog_url = catalog_url
        self.allowed_hosts = (allowed_host,) if isinstance(allowed_host, str) else allowed_host
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )

    def list_documents(self, since: date | None = None) -> list[SourceDocument]:
        del since
        response = self._request("GET", self.catalog_url)
        documents: list[SourceDocument] = []
        current_document_number: str | None = None
        current_title = ""
        current_source_url = self.catalog_url
        for href, raw_title in _extract_links(response.text):
            content_url = urljoin(self.catalog_url, href)
            if not self._is_allowed(content_url):
                continue
            match = _DOCUMENT_NUMBER_PATTERN.search(f"{content_url} {raw_title}".upper())
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
                )
            )
        return _deduplicate_documents(documents)

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


OFFICIAL_SOURCE_CATALOGS: dict[str, OfficialSourceConfig] = {
    "mof": {
        "source_name": "mof-vbpq",
        "catalog_url": "https://vbpq.mof.gov.vn/",
        "allowed_host": "vbpq.mof.gov.vn",
    },
    "government": {
        "source_name": "government-portal",
        "catalog_url": "https://vanban.chinhphu.vn/he-thong-van-ban?classid=1",
        "allowed_host": ("vanban.chinhphu.vn", "datafiles.chinhphu.vn"),
    },
}


def create_official_connector(
    source: str, client: httpx.Client | None = None
) -> OfficialPortalConnector:
    try:
        config = OFFICIAL_SOURCE_CATALOGS[source]
    except KeyError as error:
        raise ConnectorError(f"Unknown official source: {source}") from error
    return OfficialPortalConnector(**config, client=client)


_DOCUMENT_NUMBER_PATTERN = re.compile(
    r"\b\d{1,3}/\d{4}/[A-ZĐ]{1,10}-[A-ZĐ]{1,10}\b",
    re.IGNORECASE,
)


def _extract_links(html: str) -> Iterator[tuple[str, str]]:
    for match in re.finditer(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = re.sub(r"<[^>]+>", " ", match.group(2))
        yield match.group(1), " ".join(title.split())


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _deduplicate_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    unique: dict[str, SourceDocument] = {}
    for document in documents:
        unique.setdefault(document.content_url, document)
    return list(unique.values())
