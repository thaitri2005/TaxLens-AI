import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from taxlens.legal_data.document_numbers import find_document_numbers
from taxlens.retrieval.search import SearchFilters


class QueryIntent(StrEnum):
    DOCUMENT_LOOKUP = "DOCUMENT_LOOKUP"
    REGULATORY_QUESTION = "REGULATORY_QUESTION"
    CHANGE_SUMMARY = "CHANGE_SUMMARY"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    intent: QueryIntent
    filters: SearchFilters
    document_numbers: tuple[str, ...]


_UNSUPPORTED_QUERIES = {"chào", "chào bạn", "hello", "hi", "test"}


def plan_query(query: str) -> QueryPlan:
    normalized_query = " ".join(unicodedata.normalize("NFC", query).split())
    normalized_case = normalized_query.casefold()
    document_numbers = find_document_numbers(normalized_query)
    # Restricting retrieval to one document only makes sense when exactly one is named;
    # a question about several documents needs evidence from each of them.
    filters = SearchFilters(
        document_number=document_numbers[0] if len(document_numbers) == 1 else None
    )

    if not normalized_query or normalized_case in _UNSUPPORTED_QUERIES:
        intent = QueryIntent.UNSUPPORTED
    elif _contains_any(normalized_case, "thay đổi", "sửa đổi", "điểm mới"):
        intent = QueryIntent.CHANGE_SUMMARY
    # "doanh nghiệp" alone is not an impact signal: it is part of "thuế thu nhập doanh nghiệp".
    elif _contains_any(normalized_case, "ảnh hưởng", "tác động", "áp dụng cho"):
        intent = QueryIntent.IMPACT_ANALYSIS
    elif document_numbers:
        intent = QueryIntent.DOCUMENT_LOOKUP
    else:
        intent = QueryIntent.REGULATORY_QUESTION

    return QueryPlan(
        original_query=normalized_query,
        intent=intent,
        filters=filters,
        document_numbers=document_numbers,
    )


def _contains_any(query: str, *terms: str) -> bool:
    return any(term in query for term in terms)
