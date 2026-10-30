"""Ministry of Finance legal document database (vbpq.mof.gov.vn).

The ministry's database exposes a JSON API with what the government portal lacks: legal
status ("Đang hiệu lực", "Hết hiệu lực"), effective dates, and historical documents back to
the 1950s, most of which are attached as Word files whose text needs no OCR. Tax documents
are selected by the "tax, fees and charges" field (tagged until about 2016) and by the
drafting departments for tax, tax policy, and customs (which cover later documents).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from taxlens.ingestion.connectors import ConnectorError, SourceDocument
from taxlens.legal_data.document_numbers import (
    canonical_document_number,
    issuing_agency_for,
)

logger = logging.getLogger(__name__)
BASE_URL = "https://vbpq.mof.gov.vn"
SOURCE_NAME = "mof-vbpq"
SEARCH_PATH = "/api/legaldoc/Search/POSTSearchQuery"
FILE_PATH = "/DKC.FileManagement/FileStorage/File/{file_id}"

# Selections whose union is the tax corpus; documents found by several are kept once.
TAX_SELECTIONS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("tax field", {"Field": {"id": 6}}),  # Quản lý thuế, phí và lệ phí
    ("tax policy department", {"Editor": {"id": 3}}),
    ("tax department", {"Editor": {"id": 21}}),  # Cục Thuế
    ("customs department", {"Editor": {"id": 22}}),  # Cục Hải quan
)
# Normative documents. Decisions (mostly appointments and procedure lists) and official
# letters are excluded by default to keep collection and indexing costs down.
NORMATIVE_DOCUMENT_TYPES = frozenset(
    {"Thông tư", "Thông tư liên tịch", "Nghị định", "Luật", "Pháp lệnh", "Nghị quyết"}
)
CONSOLIDATED_CONTENT_TYPE = "LegalDocument_VBHN"
LEGAL_STATUSES = {
    "Đang hiệu lực": "EFFECTIVE",
    "Hết hiệu lực một phần": "PARTIALLY_EXPIRED",
    "Hết hiệu lực": "EXPIRED",
    "Chưa hiệu lực": "NOT_YET_EFFECTIVE",
    "Không xác định hiệu lực": "UNKNOWN",
}
# Preferred attachment formats: word-processor files carry exact text (no OCR).
_FILE_PREFERENCE = (".docx", ".doc", ".rtf", ".pdf")
_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".rtf": "application/rtf",
    ".pdf": "application/pdf",
}
MAX_FILE_BYTES = 60_000_000
_YEARLESS_CONSOLIDATED = re.compile(r"^\d+/VBHN-[A-ZĐ-]+$")


@dataclass(frozen=True)
class MofSearchOptions:
    issued_from: date | None = None
    include_expired: bool = False
    include_all_document_types: bool = False


class MofLegalDocumentConnector:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: httpx.Client | None = None,
        page_size: int = 100,
        delay_seconds: float = 0.5,
        retries: int = 4,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(90.0, connect=15.0),
            follow_redirects=True,
            headers={"User-Agent": "TaxLens-AI/0.1 (+https://github.com/thaitri2005/TaxLens-AI)"},
        )
        self._page_size = page_size
        self._delay_seconds = delay_seconds
        self._retries = retries

    def list_documents(self, options: MofSearchOptions | None = None) -> list[SourceDocument]:
        """Tax documents with a downloadable file, in force first and newest first."""

        options = options or MofSearchOptions()
        records: dict[int, dict[str, Any]] = {}
        for label, selection in TAX_SELECTIONS:
            for record in self._search(label, selection, options.issued_from):
                records.setdefault(int(record["id"]), record)
        documents = [
            document
            for record in records.values()
            if _is_wanted(record, options)
            and (document := _to_source_document(record)) is not None
        ]
        logger.info(
            "Ministry of Finance: kept %d of %d records (normative documents%s with a "
            "Word or PDF file)",
            len(documents),
            len(records),
            "" if options.include_expired else " not expired",
        )
        return sorted(
            documents,
            key=lambda document: (
                document.legal_status != "EFFECTIVE",
                -(document.issue_date or date.min).toordinal(),
            ),
        )

    def fetch_document(self, document: SourceDocument) -> bytes:
        parsed = urlparse(document.content_url)
        if parsed.scheme != "https" or parsed.hostname != urlparse(BASE_URL).hostname:
            raise ConnectorError(
                f"URL is outside the Ministry of Finance host: {document.content_url}"
            )
        response = self._request("GET", document.content_url)
        if len(response.content) > MAX_FILE_BYTES:
            raise ConnectorError(f"File is too large to ingest: {document.content_url}")
        return response.content

    def _search(
        self, label: str, selection: dict[str, Any], issued_from: date | None
    ) -> Iterable[dict[str, Any]]:
        page = 1
        while True:
            body: dict[str, Any] = {
                "Page": page,
                "PageSize": self._page_size,
                "ContentType": "LegalDocument",
                "ContentTypeId": 0,
                "Field": {},
                "Organization": {},
                "Editor": {},
                "DocumentStatus": {},
                "DocumentType": {},
                "DocumentTypeForbidden": {},
                **selection,
            }
            if issued_from is not None:
                # The API expects month/day/year.
                body["IssuedDateFrom"] = issued_from.strftime("%m/%d/%Y")
            payload = self._request("POST", BASE_URL + SEARCH_PATH, json=body).json()
            records = payload.get("documents") or []
            total = int(payload.get("totalItem") or 0)
            logger.info(
                "Ministry of Finance %s: page %d/%d (%d of %d records)",
                label,
                page,
                max(1, -(-total // self._page_size)),
                min(page * self._page_size, total),
                total,
            )
            yield from records
            if len(records) < self._page_size or page * self._page_size >= total:
                return
            page += 1
            time.sleep(self._delay_seconds)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                response = self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPError as error:
                # The ministry's server times out under large requests; back off and retry.
                last_error = error
                wait = self._delay_seconds * 4 * (attempt + 1)
                logger.warning(
                    "Ministry of Finance request failed (%s); attempt %d/%d, retrying in %.0fs",
                    type(error).__name__,
                    attempt + 1,
                    self._retries,
                    wait,
                )
                time.sleep(wait)
        raise ConnectorError(f"Ministry of Finance request failed: {url}") from last_error


def _is_wanted(record: dict[str, Any], options: MofSearchOptions) -> bool:
    status = LEGAL_STATUSES.get(record.get("documentStatusRecordName") or "", "UNKNOWN")
    if not options.include_expired and status == "EXPIRED":
        return False
    if options.include_all_document_types:
        return True
    return (
        record.get("contentType") == CONSOLIDATED_CONTENT_TYPE
        or record.get("documentTypeRecordName") in NORMATIVE_DOCUMENT_TYPES
    )


def _to_source_document(record: dict[str, Any]) -> SourceDocument | None:
    attachment = _preferred_attachment(record.get("filePathCurrent") or [])
    number = canonical_document_number(str(record.get("no") or ""))
    if attachment is None or not number:
        return None
    issue_date = _parse_date(record.get("legalPublishDate"))
    if _YEARLESS_CONSOLIDATED.match(number) and issue_date is not None:
        # Consolidated texts restart numbering every year: 18/VBHN-BTC of 2025 (invoices)
        # and of 2026 (VAT) are different documents.
        number = f"{number} ({issue_date.year})"
    extension = "." + attachment["inputFileName"].rsplit(".", 1)[-1].lower()
    organizations = [o["name"] for o in record.get("organizations") or [] if o.get("name")]
    content_type = record.get("contentType") or "LegalDocument"
    return SourceDocument(
        source_name=SOURCE_NAME,
        source_document_id=str(record["id"]),
        document_number=number,
        title=" ".join(str(record.get("summary") or number).split()),
        source_url=f"{BASE_URL}/Detail?contentType={content_type}&id={record['id']}",
        content_url=BASE_URL + FILE_PATH.format(file_id=attachment["id"]),
        content_type=_CONTENT_TYPES[extension],
        document_type=str(record.get("documentTypeRecordName") or "Văn bản"),
        issuing_agency=issuing_agency_for(number) or ", ".join(organizations) or None,
        issue_date=issue_date,
        legal_status=LEGAL_STATUSES.get(record.get("documentStatusRecordName") or "", "UNKNOWN"),
        effective_date=_parse_date(record.get("legalApplyDate")),
    )


def _preferred_attachment(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        file
        for file in files
        if "." + str(file.get("inputFileName", "")).rsplit(".", 1)[-1].lower() in _FILE_PREFERENCE
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda file: _FILE_PREFERENCE.index(
            "." + file["inputFileName"].rsplit(".", 1)[-1].lower()
        ),
    )


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value[:19]).date()
    except ValueError:
        return None
