from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.intelligence.chat import ChatMessage, ChatProvider, ChatProviderError, ChatRequest
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.citations import Citation, build_citation
from taxlens.retrieval.search import SearchResult


class ComparisonError(ValueError):
    """Raised when the requested documents cannot be compared."""


ChangeType = Literal["ADDED", "REMOVED", "MODIFIED", "UNCHANGED"]


@dataclass(frozen=True)
class ArticleChange:
    key: str
    change_type: ChangeType
    before_content: str | None
    after_content: str | None
    before_citation: Citation | None
    after_citation: Citation | None


@dataclass(frozen=True)
class DocumentComparison:
    before_document_number: str
    after_document_number: str
    before_version_id: str
    after_version_id: str
    changes: list[ArticleChange]


@dataclass(frozen=True)
class ComparisonSummary:
    comparison: DocumentComparison
    summary: str
    practical_impact: str
    uncertainties: list[str]
    referenced_change_keys: tuple[str, ...]


def compare_documents(
    session: Session,
    before_document_number: str,
    after_document_number: str,
) -> DocumentComparison:
    if before_document_number == after_document_number:
        raise ComparisonError("Comparison requires two different document numbers")

    before_document, before_version = _load_latest_document(session, before_document_number)
    after_document, after_version = _load_latest_document(session, after_document_number)
    before_chunks = _load_chunks(session, before_version)
    after_chunks = _load_chunks(session, after_version)

    before_by_key = _index_chunks(before_document, before_version, before_chunks)
    after_by_key = _index_chunks(after_document, after_version, after_chunks)
    changes: list[ArticleChange] = []
    for key in sorted(set(before_by_key) | set(after_by_key)):
        before = before_by_key.get(key)
        after = after_by_key.get(key)
        change_type: ChangeType
        if before is None:
            change_type = "ADDED"
        elif after is None:
            change_type = "REMOVED"
        elif before.chunk.content == after.chunk.content:
            change_type = "UNCHANGED"
        else:
            change_type = "MODIFIED"
        changes.append(
            ArticleChange(
                key=key,
                change_type=change_type,
                before_content=before.chunk.content if before else None,
                after_content=after.chunk.content if after else None,
                before_citation=build_citation(before) if before else None,
                after_citation=build_citation(after) if after else None,
            )
        )

    return DocumentComparison(
        before_document_number=before_document.document_number,
        after_document_number=after_document.document_number,
        before_version_id=str(before_version.id),
        after_version_id=str(after_version.id),
        changes=changes,
    )


def summarize_comparison(
    comparison: DocumentComparison,
    chat_provider: ChatProvider,
) -> ComparisonSummary:
    try:
        response = chat_provider.complete(ChatRequest(messages=_build_summary_messages(comparison)))
    except ChatProviderError as error:
        raise ComparisonError("The configured language model is unavailable") from error

    try:
        payload = _parse_summary(response.content)
    except ValueError as error:
        raise ComparisonError("The model returned an invalid comparison summary") from error
    valid_keys = {change.key for change in comparison.changes}
    referenced_keys = tuple(payload["referenced_change_keys"])
    if not set(referenced_keys).issubset(valid_keys):
        raise ComparisonError("The model referenced an unknown comparison section")
    return ComparisonSummary(
        comparison=comparison,
        summary=payload["summary"],
        practical_impact=payload["practical_impact"],
        uncertainties=payload["uncertainties"],
        referenced_change_keys=referenced_keys,
    )


def _load_latest_document(
    session: Session,
    document_number: str,
) -> tuple[LegalDocument, DocumentVersion]:
    document = session.execute(
        select(LegalDocument).where(LegalDocument.document_number == document_number)
    ).scalar_one_or_none()
    if document is None:
        raise ComparisonError(f"Document not found: {document_number}")
    versions = (
        session.execute(select(DocumentVersion).where(DocumentVersion.document_id == document.id))
        .scalars()
        .all()
    )
    if not versions:
        raise ComparisonError(f"Document has no versions: {document_number}")
    version = max(versions, key=lambda item: item.effective_date or date.min)
    return document, version


def _build_summary_messages(comparison: DocumentComparison) -> list[ChatMessage]:
    change_blocks = "\n\n".join(
        (
            f"Key: {change.key}\nChange: {change.change_type}\n"
            f"Before ({comparison.before_document_number}): {change.before_content or '[none]'}\n"
            f"After ({comparison.after_document_number}): {change.after_content or '[none]'}"
        )
        for change in comparison.changes
    )
    return [
        ChatMessage(
            role="system",
            content=(
                "You summarize a deterministic Vietnamese tax-document diff. Use only the supplied "
                "before and after text. Return JSON with summary, practical_impact, uncertainties, "
                "and referenced_change_keys. Do not invent obligations or legal conclusions."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Before document: {comparison.before_document_number}\n"
                f"After document: {comparison.after_document_number}\n\n{change_blocks}"
            ),
        ),
    ]


def _parse_summary(content: str) -> dict[str, Any]:
    import json

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Summary is not JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Summary must be a JSON object")
    required_text = {}
    for name in ("summary", "practical_impact"):
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty")
        required_text[name] = value.strip()
    uncertainties = payload.get("uncertainties")
    referenced_keys = payload.get("referenced_change_keys")
    if not isinstance(uncertainties, list) or not all(
        isinstance(item, str) and item.strip() for item in uncertainties
    ):
        raise ValueError("uncertainties must be text values")
    if not isinstance(referenced_keys, list) or not all(
        isinstance(item, str) and item.strip() for item in referenced_keys
    ):
        raise ValueError("referenced_change_keys must be text values")
    return {
        **required_text,
        "uncertainties": [item.strip() for item in uncertainties],
        "referenced_change_keys": [item.strip() for item in referenced_keys],
    }


def _load_chunks(session: Session, version: DocumentVersion) -> list[DocumentChunk]:
    return list(
        session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == version.id)
            .order_by(DocumentChunk.article_number, DocumentChunk.clause_number, DocumentChunk.id)
        ).scalars()
    )


def _index_chunks(
    document: LegalDocument,
    version: DocumentVersion,
    chunks: list[DocumentChunk],
) -> dict[str, SearchResult]:
    indexed: dict[str, SearchResult] = {}
    for chunk in chunks:
        base_key = (
            f"article:{chunk.article_number or 'unknown'}|clause:{chunk.clause_number or 'unknown'}"
        )
        key = base_key
        duplicate_number = 2
        while key in indexed:
            key = f"{base_key}|part:{duplicate_number}"
            duplicate_number += 1
        indexed[key] = SearchResult(chunk=chunk, version=version, document=document)
    return indexed
