import hashlib
import re
import unicodedata
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from taxlens.config import get_settings
from taxlens.document_processing.formats import detect_format, extract_word_processor_text
from taxlens.document_processing.ocr import ocr_pages
from taxlens.legal_data.document_numbers import find_document_numbers
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
    ProcessingJob,
)
from taxlens.retrieval.text import fold_vietnamese
from taxlens.storage.base import ObjectStorage

# Article headings: "Điều 5. Thuế suất", "Điều 5a: ...", and OCR variants such as
# "| Điều 5.", "-_.. Điêu 15." or "Điều 9, Thời điểm". A short run of non-word noise may
# precede the keyword, but not a quotation mark: quoted articles are amendment text that
# belongs to the enclosing article of the amending document.
ARTICLE_PATTERN = re.compile(
    r"(?mi)^(?:[^\w\n\"'“”‘’]|_){0,6}(?:article|đi[eêềệ]u)"
    r"[ \t]*(\d{1,3}[a-zđ]?)[ \t]*([.:,])[ \t]*(.*)$"
)
# Clause numbers "1.", "2." at line start; OCR may add leading noise or read "." as ",".
CLAUSE_PATTERN = re.compile(r"(?m)^(?:[^\w\n]|_){0,6}(\d{1,3})[.,]\s+(?=[^\W\d_])")
# Section headings of documents without articles: "PHẦN A ...", "Chương II ...", or a
# Roman-numeral heading "I. ĐỐI TƯỢNG ÁP DỤNG" (the title must start in uppercase).
SECTION_PATTERN = re.compile(
    r"(?m)^[ \t]*(?:(?:PHẦN|Phần|CHƯƠNG|Chương|MỤC|Mục)[ \t]+(?:[IVXLC]+|\d+|[A-ZĐ])\b.*"
    r"|(?P<roman>[IVXL]{1,6})[ \t]*[\./][ \t]+(?=[A-ZĐÀ-Ỹ]).*)$"
)
# Words that make "Điều 8, khoản 4 ..." a cross-reference rather than a heading.
_REFERENCE_WORDS = ("khoản", "điều", "điểm", "mục", "chương")
PAGE_SEPARATOR = "\n\f\n"
# Keeps a chunk (plus its heading and the "passage: " prefix) inside the embedding model's
# 512-token window for Vietnamese text.
MAX_CHUNK_CHARACTERS = 1500
# Article introductions up to this length stay with clause 1 instead of standing alone.
MAX_MERGED_INTRO_CHARACTERS = 400
MIN_PREAMBLE_CHARACTERS = 20
# Bump when chunking changes; processed versions with an older stage suffix are re-chunked
# from stored text by ``process_corpus.py --rechunk-outdated``.
CHUNKER_VERSION = 3
CHUNKER_STAGE_SUFFIX = f":v{CHUNKER_VERSION}"
_HEADER_NUMBER_PATTERN = re.compile(r"(?i)\bs[ốóôo]\s*(?:hiệu)?\s*[:.]\s*(\S{3,40})")


@dataclass(frozen=True)
class ProcessResult:
    status: str
    version_id: str
    chunk_count: int
    error_code: str | None = None
    extraction_method: str | None = None


def process_document_version(
    session: Session,
    storage: ObjectStorage,
    version: DocumentVersion,
    force: bool = False,
    reextract: bool = False,
) -> ProcessResult:
    """Extract, normalize, and chunk one document version.

    With ``force``, an already processed version is re-chunked from its stored normalized
    text, so chunking changes do not repeat PDF extraction or OCR. ``reextract`` repeats
    extraction and OCR instead (after OCR settings change).
    """

    existing_chunks = session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
    ).all()
    force = force or reextract
    if (
        not force
        and version.normalized_content_hash is not None
        and any(chunk.content.strip() for chunk in existing_chunks)
    ):
        return ProcessResult(
            status="UNCHANGED",
            version_id=str(version.id),
            chunk_count=len(existing_chunks),
            extraction_method="unchanged",
        )

    if (
        force
        and not reextract
        and version.normalized_artifact_key is not None
        and storage.exists(version.normalized_artifact_key)
    ):
        normalized_text = storage.get_bytes(version.normalized_artifact_key).decode("utf-8")
        stored_pages = [
            unicodedata.normalize("NFC", page)
            for page in normalized_text.rstrip().split(PAGE_SEPARATOR)
        ]
        chunk_count = _replace_chunks(session, version, existing_chunks, stored_pages)
        job = _latest_job(session, version)
        if job is not None:
            base_stage = job.stage.split(":", 1)[0]
            _complete_job(
                session,
                version,
                job,
                base_stage if base_stage.endswith("CHUNKED") else "CHUNKED",
                stored_pages,
            )
        session.commit()
        return ProcessResult(
            status="PROCESSED",
            version_id=str(version.id),
            chunk_count=chunk_count,
            extraction_method="rechunked",
        )

    try:
        raw_content = storage.get_bytes(version.raw_artifact_key)
    except Exception as error:
        return _record_failure(
            session, version, existing_chunks, "RAW_ARTIFACT_UNAVAILABLE", error, "unavailable"
        )

    used_ocr = False
    try:
        pages = extract_pages(raw_content, version.raw_artifact_key)
        settings = get_settings()
        # OCR only the pages without a usable text layer: a digital PDF with a few scanned
        # appendix pages should not be OCR'd in full.
        scanned_pages = [index for index, page in enumerate(pages) if not _has_usable_text([page])]
        if scanned_pages and raw_content.startswith(b"%PDF") and settings.ocr_enabled:
            for index, text in ocr_pages(raw_content, settings, scanned_pages).items():
                pages[index] = text
            used_ocr = True
        if not _has_usable_text(pages):
            raise ValueError(
                "No usable text found after Tesseract OCR"
                if used_ocr
                else "No usable extractable text found"
            )
    except Exception as error:
        is_pdf = raw_content.startswith(b"%PDF")
        error_code = (
            "OCR_REQUIRED"
            if version.raw_artifact_key.casefold().endswith(".pdf") and is_pdf
            else "DOCUMENT_EXTRACTION_FAILED"
        )
        return _record_failure(
            session,
            version,
            existing_chunks,
            error_code,
            error,
            "ocr_failed" if is_pdf else "native_failed",
        )

    normalized_pages = [normalize_text(page).strip() for page in pages]
    # Only trailing whitespace is stripped: stripping a leading empty page would shift every
    # page boundary.
    normalized_text = PAGE_SEPARATOR.join(normalized_pages).rstrip() + "\n"
    normalized_content = normalized_text.encode("utf-8")
    normalized_hash = hashlib.sha256(normalized_content).hexdigest()
    normalized_key = f"normalized-text/{normalized_hash}.txt"
    if not storage.exists(normalized_key):
        storage.put_bytes(normalized_key, normalized_content, "text/plain; charset=utf-8")

    chunk_count = _replace_chunks(session, version, existing_chunks, normalized_pages)
    version.normalized_content_hash = normalized_hash
    version.normalized_artifact_key = normalized_key
    job = _latest_job(session, version)
    if job is not None:
        _complete_job(
            session, version, job, "OCR_CHUNKED" if used_ocr else "CHUNKED", normalized_pages
        )
    session.commit()
    return ProcessResult(
        status="PROCESSED",
        version_id=str(version.id),
        chunk_count=chunk_count,
        extraction_method="ocr" if used_ocr else "native",
    )


def _complete_job(
    session: Session,
    version: DocumentVersion,
    job: ProcessingJob,
    stage: str,
    pages: list[str],
) -> None:
    job.status = "COMPLETED"
    job.stage = f"{stage}{CHUNKER_STAGE_SUFFIX}"
    job.error_code = None
    job.error_detail = None
    document = session.get(LegalDocument, version.document_id)
    header_number = header_document_number(pages[0] if pages else "")
    if document is not None and header_number and not _same_number(
        header_number, document.document_number
    ):
        # Catalog listings have attached the wrong number before (an amending decree filed
        # under the decree it amends); surface it instead of silently citing the wrong one.
        job.error_code = "DOCUMENT_NUMBER_MISMATCH"
        job.error_detail = (
            f"Document header reads {header_number}; stored as {document.document_number}"
        )


def header_document_number(first_page: str) -> str | None:
    """The document's own number from its header line ("Số: 32/2025/TT-BTC")."""

    for match in _HEADER_NUMBER_PATTERN.finditer(first_page[:2500]):
        numbers = find_document_numbers(match.group(1))
        if numbers:
            return numbers[0]
    return None


def _same_number(left: str, right: str) -> bool:
    def key(value: str) -> str:
        return "/".join(part.lstrip("0") for part in fold_vietnamese(value).upper().split("/"))

    return key(left) == key(right)


def mark_processing_failed(session: Session, version_id: object, error: Exception) -> ProcessResult:
    """Record an unexpected processing error so the version stops blocking the queue."""

    session.rollback()
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise error
    job = _latest_job(session, version) or _new_job(session, version)
    job.status = "FAILED"
    job.stage = "PROCESSING"
    job.error_code = "PROCESSING_ERROR"
    job.error_detail = f"{type(error).__name__}: {error}"[:2000]
    job.attempt_count += 1
    session.commit()
    return ProcessResult(
        status="FAILED",
        version_id=str(version.id),
        chunk_count=0,
        error_code="PROCESSING_ERROR",
    )


@dataclass(frozen=True)
class ParsedChunk:
    article_number: str | None
    heading: str | None
    content: str
    page_start: int | None = None
    page_end: int | None = None
    clause_number: str | None = None


def normalize_text(raw_text: str) -> str:
    # PDF text layers may use decomposed Vietnamese characters; queries arrive composed.
    raw_text = unicodedata.normalize("NFC", raw_text)
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
    return "\n".join(normalized_lines).strip() + "\n"


def _has_usable_text(pages: list[str]) -> bool:
    text = " ".join(page.strip() for page in pages)
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 40:
        return False
    alphabetic = sum(character.isalpha() for character in compact)
    return alphabetic / len(compact) >= 0.2


def extract_pages(raw_content: bytes, artifact_key: str) -> list[str]:
    """Pages of a PDF, or the whole text of a Word, RTF, DOCX, or plain-text document."""

    document_format = detect_format(raw_content)
    if document_format == "pdf":
        reader = PdfReader(BytesIO(raw_content))
        return [page.extract_text() or "" for page in reader.pages]
    if document_format in ("doc", "rtf", "docx"):
        return [extract_word_processor_text(raw_content)]
    return [raw_content.decode("utf-8", errors="replace")]


def is_paginated(artifact_key: str) -> bool:
    """Only PDFs have meaningful page numbers; Word and text files are one flow of text."""

    return artifact_key.casefold().endswith(".pdf")


def extract_text(raw_content: bytes, artifact_key: str) -> str:
    return "\n".join(extract_pages(raw_content, artifact_key))


def build_article_chunks(
    text: str,
    page_boundaries: list[int] | None = None,
    max_characters: int = MAX_CHUNK_CHARACTERS,
) -> list[ParsedChunk]:
    """Split legal text into article chunks, and long articles into clause chunks."""

    # Documents from before about 2011 are often organized as "Phần / I. / 1." without
    # "Điều" articles; their section headings become the structure instead.
    headings = find_article_headings(text) or find_section_headings(text)
    chunks: list[ParsedChunk] = []

    # Text before the first article holds the title, issuing body, and legal bases.
    preamble_end = headings[0].start if headings else len(text)
    preamble = text[:preamble_end]
    if not headings or len("".join(preamble.split())) >= MIN_PREAMBLE_CHARACTERS:
        for start, end in _split_span(text, 0, preamble_end, max_characters):
            chunks.append(_parsed_chunk(text, page_boundaries, start, end, None, None, None))

    for index, heading in enumerate(headings):
        article_end = headings[index + 1].start if index + 1 < len(headings) else len(text)
        for segment_start, segment_end, clause_number in _article_segments(
            text, heading.start, heading.end, article_end, max_characters
        ):
            for start, end in _split_span(text, segment_start, segment_end, max_characters):
                chunks.append(
                    _parsed_chunk(
                        text,
                        page_boundaries,
                        start,
                        end,
                        heading.number,
                        heading.title,
                        clause_number,
                    )
                )
    return chunks


@dataclass(frozen=True)
class ArticleHeading:
    start: int
    end: int
    number: str | None
    """Article number; None for a section heading of a document without articles."""
    title: str | None


def find_article_headings(text: str) -> list[ArticleHeading]:
    """Find article headings, rejecting cross-references and out-of-order matches."""

    headings: list[ArticleHeading] = []
    previous_number = 0
    for match in ARTICLE_PATTERN.finditer(text):
        number = match.group(1)
        separator = match.group(2)
        # Titles never start with digits or punctuation; OCR leaves "22.8 Trách nhiệm".
        title = re.sub(r"^[\W\d_]+", "", match.group(3)).strip()
        if separator == ",":
            first_word = title.split(" ", 1)[0].casefold() if title else ""
            if not title or not title[0].isupper() or first_word in _REFERENCE_WORDS:
                continue
        if not title and _continues_sentence(text, match.start()):
            # "... tại khoản 1\nĐiều 19." is a reference wrapped onto its own line.
            continue
        numeric = int("".join(character for character in number if character.isdigit()))
        # Articles are numbered upwards; a smaller or repeated number is a reference such
        # as "Điều 3 của Nghị định ..." that happens to start a line.
        if numeric <= previous_number:
            continue
        previous_number = numeric
        headings.append(
            ArticleHeading(
                start=match.start(), end=match.end(), number=number, title=title or None
            )
        )
    return headings


def find_section_headings(text: str) -> list[ArticleHeading]:
    """Section headings ("PHẦN A", "Chương II", "I. ĐỐI TƯỢNG ÁP DỤNG") in order.

    Roman numerals must increase by one, or restart at I under a new part, which rejects
    numbered list items that happen to look like headings.
    """

    headings: list[ArticleHeading] = []
    previous_roman = 0
    for match in SECTION_PATTERN.finditer(text):
        line = match.group(0).strip()
        roman = match.group("roman")
        if roman is not None:
            value = _roman_value(roman)
            if value not in (previous_roman + 1, 1):
                continue
            previous_roman = value
        else:
            previous_roman = 0
        headings.append(
            ArticleHeading(start=match.start(), end=match.end(), number=None, title=line[:200])
        )
    return headings


def _roman_value(numeral: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for index, character in enumerate(numeral):
        value = values[character]
        following = values[numeral[index + 1]] if index + 1 < len(numeral) else 0
        total += -value if value < following else value
    return total


def _continues_sentence(text: str, line_start: int) -> bool:
    previous_line = text[:line_start].rstrip("\n\f ").rsplit("\n", 1)[-1].strip()
    return bool(previous_line) and previous_line[-1] not in ".;:!?”\"')"


def _article_segments(
    text: str, article_start: int, body_start: int, article_end: int, max_characters: int
) -> list[tuple[int, int, str | None]]:
    if article_end - article_start <= max_characters:
        return [(article_start, article_end, None)]

    # Clauses are numbered 1., 2., 3. within an article; requiring the sequence filters out
    # wrapped lines that happen to start with a number.
    clause_starts: list[tuple[int, str]] = []
    for clause in CLAUSE_PATTERN.finditer(text, body_start, article_end):
        if int(clause.group(1)) == len(clause_starts) + 1:
            clause_starts.append((clause.start(), clause.group(1)))
    if len(clause_starts) == 1:
        # A lone "1." is more likely a numbered list item than clause structure.
        clause_starts = []
    if not clause_starts:
        return [(article_start, article_end, None)]

    segments: list[tuple[int, int, str | None]] = []
    first_clause_start = clause_starts[0][0]
    if first_clause_start - article_start > MAX_MERGED_INTRO_CHARACTERS:
        segments.append((article_start, first_clause_start, None))
        first_segment_start = first_clause_start
    else:
        first_segment_start = article_start
    for position, (clause_start, clause_number) in enumerate(clause_starts):
        segment_start = first_segment_start if position == 0 else clause_start
        segment_end = (
            clause_starts[position + 1][0] if position + 1 < len(clause_starts) else article_end
        )
        segments.append((segment_start, segment_end, clause_number))
    return segments


def _split_span(text: str, start: int, end: int, max_characters: int) -> list[tuple[int, int]]:
    """Split text[start:end] at line (or word) boundaries into spans of bounded length."""

    start, end = _trim(text, start, end)
    spans: list[tuple[int, int]] = []
    while end - start > max_characters:
        window_end = start + max_characters
        minimum_split = start + max_characters // 2
        split_at = text.rfind("\n", minimum_split, window_end)
        if split_at < 0:
            split_at = text.rfind(" ", minimum_split, window_end)
        if split_at < 0:
            split_at = window_end
        span = _trim(text, start, split_at)
        if span[0] < span[1]:
            spans.append(span)
        start, end = _trim(text, split_at, end)
    if start < end:
        spans.append((start, end))
    return spans


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _parsed_chunk(
    text: str,
    page_boundaries: list[int] | None,
    start: int,
    end: int,
    article_number: str | None,
    heading: str | None,
    clause_number: str | None,
) -> ParsedChunk:
    return ParsedChunk(
        article_number=article_number,
        heading=heading,
        clause_number=clause_number,
        content=text[start:end],
        page_start=_page_for_offset(page_boundaries, start) if page_boundaries else None,
        page_end=(
            _page_for_offset(page_boundaries, max(end - 1, start)) if page_boundaries else None
        ),
    )


def _replace_chunks(
    session: Session,
    version: DocumentVersion,
    existing_chunks: Sequence[DocumentChunk],
    normalized_pages: list[str],
) -> int:
    _delete_chunks_and_embeddings(session, version.id, existing_chunks)
    normalized_text = PAGE_SEPARATOR.join(normalized_pages)
    page_boundaries = (
        _page_boundaries(normalized_pages) if is_paginated(version.raw_artifact_key) else None
    )
    chunks = build_article_chunks(normalized_text, page_boundaries)
    for chunk in chunks:
        session.add(
            DocumentChunk(
                document_version_id=version.id,
                article_number=chunk.article_number,
                clause_number=chunk.clause_number,
                heading=chunk.heading,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content=chunk.content,
                token_count=len(chunk.content.split()),
            )
        )
    return len(chunks)


def _record_failure(
    session: Session,
    version: DocumentVersion,
    existing_chunks: Sequence[DocumentChunk],
    error_code: str,
    error: Exception,
    extraction_method: str,
) -> ProcessResult:
    _delete_chunks_and_embeddings(session, version.id, existing_chunks)
    version.normalized_content_hash = None
    version.normalized_artifact_key = None
    # Without a FAILED job the version would be selected again on every run.
    job = _latest_job(session, version) or _new_job(session, version)
    job.status = "FAILED"
    job.stage = "EXTRACTION"
    job.error_code = error_code
    job.error_detail = str(error)[:2000]
    job.attempt_count += 1
    session.commit()
    return ProcessResult(
        status="FAILED",
        version_id=str(version.id),
        chunk_count=0,
        error_code=error_code,
        extraction_method=extraction_method,
    )


def _page_boundaries(pages: list[str]) -> list[int]:
    boundaries: list[int] = []
    offset = 0
    for page in pages:
        boundaries.append(offset)
        offset += len(page) + len(PAGE_SEPARATOR)
    return boundaries


def _page_for_offset(boundaries: list[int], offset: int) -> int:
    return bisect_right(boundaries, offset)


def _latest_job(session: Session, version: DocumentVersion) -> ProcessingJob | None:
    return session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_version_id == version.id)
        .order_by(ProcessingJob.created_at.desc())
    )


def _new_job(session: Session, version: DocumentVersion) -> ProcessingJob:
    job = ProcessingJob(
        document_version_id=version.id, status="PENDING", stage="DOWNLOADED", attempt_count=0
    )
    session.add(job)
    return job


def _delete_chunks_and_embeddings(
    session: Session, version_id: object, chunks: Sequence[DocumentChunk]
) -> None:
    chunk_ids = [chunk.id for chunk in chunks]
    if chunk_ids:
        session.execute(
            delete(DocumentEmbedding).where(DocumentEmbedding.document_chunk_id.in_(chunk_ids))
        )
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == version_id))
