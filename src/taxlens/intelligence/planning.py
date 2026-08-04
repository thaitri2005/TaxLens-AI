import re
from dataclasses import dataclass
from enum import StrEnum

from taxlens.retrieval.search import SearchFilters


class QueryIntent(StrEnum):
    DOCUMENT_LOOKUP = "DOCUMENT_LOOKUP"
    REGULATORY_QUESTION = "REGULATORY_QUESTION"
    CHANGE_SUMMARY = "CHANGE_SUMMARY"
    DOCUMENT_COMPARISON = "DOCUMENT_COMPARISON"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    intent: QueryIntent
    filters: SearchFilters
    document_numbers: tuple[str, ...]


_DOCUMENT_NUMBER_PATTERN = re.compile(r"\b\d{1,3}/\d{4}/[A-ZĐ]{1,10}-[A-ZĐ]{1,10}\b")
_UNSUPPORTED_QUERIES = {"chào", "chào bạn", "hello", "hi", "test"}


def plan_query(query: str) -> QueryPlan:
    normalized_query = " ".join(query.split())
    normalized_case = normalized_query.casefold()
    document_numbers = tuple(
        dict.fromkeys(
            match.group(0) for match in _DOCUMENT_NUMBER_PATTERN.finditer(normalized_query.upper())
        )
    )
    filters = SearchFilters(document_number=document_numbers[0] if document_numbers else None)

    if not normalized_query or normalized_case in _UNSUPPORTED_QUERIES:
        intent = QueryIntent.UNSUPPORTED
    elif len(document_numbers) >= 2 and _contains_any(normalized_case, "so sánh", "khác nhau"):
        intent = QueryIntent.DOCUMENT_COMPARISON
    elif _contains_any(normalized_case, "thay đổi", "sửa đổi", "điểm mới"):
        intent = QueryIntent.CHANGE_SUMMARY
    elif _contains_any(normalized_case, "ảnh hưởng", "tác động", "áp dụng cho", "doanh nghiệp"):
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
