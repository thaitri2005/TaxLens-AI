import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from taxlens.legal_data.document_numbers import find_document_numbers
from taxlens.retrieval.repeals import today_in_vietnam
from taxlens.retrieval.search import SearchFilters


class QueryIntent(StrEnum):
    DOCUMENT_LOOKUP = "DOCUMENT_LOOKUP"
    REGULATORY_QUESTION = "REGULATORY_QUESTION"
    CHANGE_SUMMARY = "CHANGE_SUMMARY"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class QuestionPeriod:
    """The span of the dates a question names, from the first day of the earliest to the
    last day of the latest (a month, quarter, or year counts as its whole span)."""

    start: date
    end: date


@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    intent: QueryIntent
    filters: SearchFilters
    document_numbers: tuple[str, ...]
    period: QuestionPeriod | None = None


_UNSUPPORTED_QUERIES = {"chào", "chào bạn", "hello", "hi", "test"}
# "ngày 15/3/2026", "ngày 15 tháng 3 năm 2026", "tháng 3/2026", "tháng 3 năm 2026",
# "quý II/2026", "quý 2 năm 2026", "năm 2026", on lower-case NFC text.
_DATE = re.compile(
    r"ngày\s+(?P<day>\d{1,2})\s*(?:/|-|tháng)\s*(?P<day_month>\d{1,2})\s*(?:/|-|năm)\s*"
    r"(?P<day_year>\d{4})"
    r"|tháng\s+(?P<month>\d{1,2})\s*(?:/|-|năm)\s*(?P<month_year>\d{4})"
    r"|quý\s+(?P<quarter>iv|i{1,3}|[1-4])\s*(?:/|-|năm)?\s*(?P<quarter_year>\d{4})"
    r"|năm\s+(?P<year>\d{4})"
)
_QUARTERS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "1": 1, "2": 2, "3": 3, "4": 4}
# A date right after a document number is its issue date ("Nghị định 123/2020/NĐ-CP ngày
# 19/10/2020"), not when the question's facts happen.
_DOCUMENT_BEFORE = re.compile(r"\d{1,4}/\d{4}/\S+[^.;,]{0,30}$")
_EARLIEST_YEAR = 1990


def plan_query(query: str, today: date | None = None) -> QueryPlan:
    normalized_query = " ".join(unicodedata.normalize("NFC", query).split())
    normalized_case = normalized_query.casefold()
    document_numbers = find_document_numbers(normalized_query)
    today = today or today_in_vietnam()
    period = question_period(normalized_case, today)
    # Restricting retrieval to one document only makes sense when exactly one is named;
    # a question about several documents needs evidence from each of them.
    # Answers state the law of the question's period, or of today: documents whose end is
    # confirmed by its start are left out, and versions taking effect after its end. When
    # the question names documents, they are kept and their endings noted.
    filters = SearchFilters(
        document_number=document_numbers[0] if len(document_numbers) == 1 else None,
        current_on=None if document_numbers else (period.start if period else today),
        as_of=period.end if period and period.end < today and not document_numbers else None,
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
        period=period,
    )


def question_period(text: str, today: date) -> QuestionPeriod | None:
    """The period of the dates in a lower-case question, ending no later than today."""

    spans: list[tuple[date, date]] = []
    for match in _DATE.finditer(text):
        if _DOCUMENT_BEFORE.search(text[max(0, match.start() - 60) : match.start()]):
            continue
        span = _span(match)
        if span and _EARLIEST_YEAR <= span[0].year and span[0] <= today:
            spans.append(span)
    if not spans:
        return None
    return QuestionPeriod(
        start=min(start for start, _ in spans), end=min(max(end for _, end in spans), today)
    )


def _span(match: re.Match[str]) -> tuple[date, date] | None:
    try:
        if match["day"]:
            day = date(int(match["day_year"]), int(match["day_month"]), int(match["day"]))
            return day, day
        if match["month"]:
            year, month = int(match["month_year"]), int(match["month"])
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        if match["quarter"]:
            year, quarter = int(match["quarter_year"]), _QUARTERS[match["quarter"]]
            last_month = quarter * 3
            return (
                date(year, last_month - 2, 1),
                date(year, last_month, calendar.monthrange(year, last_month)[1]),
            )
        year = int(match["year"])
        return date(year, 1, 1), date(year, 12, 31)
    except ValueError:
        return None


def _contains_any(query: str, *terms: str) -> bool:
    return any(term in query for term in terms)
