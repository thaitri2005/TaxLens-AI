from dataclasses import dataclass
from datetime import date
from uuid import UUID

from taxlens.retrieval.search import SearchResult


@dataclass(frozen=True)
class Citation:
    document_id: UUID
    version_id: UUID
    document_number: str
    title: str
    heading: str | None
    version_label: str | None
    legal_status: str
    effective_date: date | None
    article_number: str | None
    clause_number: str | None
    page_start: int | None
    page_end: int | None
    source_artifact_key: str
    source_url: str | None


def build_citation(result: SearchResult) -> Citation:
    return Citation(
        document_id=result.document.id,
        version_id=result.version.id,
        document_number=result.document.document_number,
        title=result.document.title,
        heading=result.chunk.heading,
        version_label=result.version.version_label,
        legal_status=result.version.legal_status,
        effective_date=result.version.effective_date,
        article_number=result.chunk.article_number,
        clause_number=result.chunk.clause_number,
        page_start=result.chunk.page_start,
        page_end=result.chunk.page_end,
        source_artifact_key=result.version.raw_artifact_key,
        source_url=result.source_url,
    )
