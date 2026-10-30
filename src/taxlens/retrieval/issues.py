"""Issue-guided retrieval: search once per legal issue a question raises.

A taxpayer's question often needs several provisions that share few words with it: the
rate, the exemption that overrides it, a definition in another document, the procedure.
One query ranks the provision closest to the question's wording and crowds out the rest.
Here a model lists the legal issues first (``decompose_question``), each issue is
searched with the same hybrid search as the baseline, and the rankings are interleaved
(``interleave``) so that every issue gets passages within the same budget K.

Decompositions are made once and stored with the evaluation data, so a run is
reproducible and calls no model.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from taxlens.intelligence.chat import ChatMessage, ChatProvider, ChatRequest
from taxlens.retrieval.embeddings import EmbeddingProvider
from taxlens.retrieval.search import SearchFilters, SearchResult, hybrid_search_chunks

# v1 wrote whole questions that repeated the situation's amounts and dates; keyword search
# keeps only the first terms, and the issues barely differed from the question.
PROMPT_VERSION = "issues-v2"
MAX_ISSUES = 4
_SYSTEM_PROMPT = """Bạn là chuyên gia pháp luật thuế Việt Nam. Người nộp thuế mô tả một tình huống.
Hãy liệt kê các vấn đề pháp lý riêng biệt cần tra cứu để trả lời đúng, theo thứ tự quan trọng:
đối tượng chịu thuế hoặc không chịu thuế, thuế suất, trường hợp ngoại lệ hoặc quy định tạm thời,
định nghĩa của khái niệm được dùng, thời điểm và thủ tục kê khai, quy định chuyển tiếp theo ngày.
Với mỗi vấn đề, viết một truy vấn tìm kiếm:
- là cụm từ ngắn (tối đa 12 từ) theo cách văn bản pháp luật diễn đạt, không phải câu hỏi;
- gọi sự vật theo nhóm mà luật dùng (ví dụ "sản phẩm rừng trồng chưa qua chế biến" thay cho tên
  một loại gỗ cụ thể), không lặp lại số tiền, ngày tháng hay tên doanh nghiệp;
- các truy vấn phải khác nhau về nội dung pháp lý;
- không ghi số hiệu văn bản, số điều hoặc số khoản.
Tối đa {max_issues} vấn đề; một tình huống đơn giản có thể chỉ có một hoặc hai vấn đề.
Chỉ trả về JSON: {{"issues": [{{"issue": "...", "query": "..."}}]}}"""


@dataclass(frozen=True)
class Issue:
    issue: str
    query: str


def decompose_question(
    question: str,
    chat: ChatProvider,
    as_of_date: date | None = None,
    max_issues: int = MAX_ISSUES,
) -> list[Issue]:
    """The legal issues a question raises, each with a search query.

    Document and article numbers are forbidden in the queries, so retrieval is credited
    for finding provisions, not the model for remembering them.
    """

    situation = (
        question if as_of_date is None else f"Ngày áp dụng: {as_of_date:%d/%m/%Y}.\n{question}"
    )
    response = chat.complete(
        ChatRequest(
            messages=[
                ChatMessage("system", _SYSTEM_PROMPT.format(max_issues=max_issues)),
                ChatMessage("user", situation),
            ],
            max_output_tokens=600,
            temperature=0.0,
        )
    )
    return parse_issues(response.content, max_issues)


def parse_issues(content: str, max_issues: int = MAX_ISSUES) -> list[Issue]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match is None:
        return []
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items = payload.get("issues") if isinstance(payload, dict) else None
    issues: list[Issue] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if query and all(query != existing.query for existing in issues):
            issues.append(Issue(issue=str(item.get("issue") or "").strip(), query=query))
    return issues[:max_issues]


def issue_guided_search(
    session: Session,
    question: str,
    issues: Sequence[Issue],
    provider: EmbeddingProvider | None,
    filters: SearchFilters | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    """The question's own ranking interleaved with one ranking per issue, ``limit`` long.

    Each search asks for ``limit`` passages, so any budget K up to ``limit`` is filled the
    same way: the first K passages of the merged ranking.
    """

    rankings = [
        hybrid_search_chunks(session, query, provider, filters, limit)
        for query in (question, *(issue.query for issue in issues))
    ]
    return interleave(rankings, limit)


def interleave(rankings: Sequence[Sequence[SearchResult]], limit: int) -> list[SearchResult]:
    """Take the next unseen passage from each ranking in turn until ``limit`` are taken."""

    merged: list[SearchResult] = []
    seen: set[object] = set()
    depth = max((len(ranking) for ranking in rankings), default=0)
    for position in range(depth):
        for ranking in rankings:
            if position >= len(ranking):
                continue
            result = ranking[position]
            if result.chunk.id in seen:
                continue
            seen.add(result.chunk.id)
            merged.append(result)
            if len(merged) == limit:
                return merged
    return merged
