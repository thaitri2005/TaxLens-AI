from datetime import date
from types import SimpleNamespace

from taxlens.intelligence.chat import ChatRequest, ChatResponse
from taxlens.retrieval.issues import Issue, decompose_question, interleave, parse_issues


def test_interleave_takes_each_ranking_in_turn_and_skips_repeats() -> None:
    question = [_result("a"), _result("b"), _result("c")]
    rate = [_result("b"), _result("d")]
    exemption = [_result("e")]

    merged = interleave([question, rate, exemption], limit=4)

    assert [result.chunk.id for result in merged] == ["a", "b", "e", "d"]
    assert len(interleave([question, rate, exemption], limit=10)) == 5


def test_parse_issues_reads_json_inside_text_and_drops_repeated_queries() -> None:
    content = (
        'Kết quả:\n{"issues": [{"issue": "Thuế suất", "query": "thuế suất nước giải khát"},'
        ' {"issue": "Lặp", "query": "thuế suất nước giải khát"},'
        ' {"issue": "Giảm thuế", "query": "giảm thuế giá trị gia tăng 2026"}, "x"]}'
    )

    assert parse_issues(content) == [
        Issue("Thuế suất", "thuế suất nước giải khát"),
        Issue("Giảm thuế", "giảm thuế giá trị gia tăng 2026"),
    ]
    assert parse_issues("không có JSON") == []
    assert parse_issues('{"issues": [') == []


def test_decompose_question_gives_the_date_and_caps_the_issues() -> None:
    requests: list[ChatRequest] = []

    class Chat:
        def complete(self, request: ChatRequest) -> ChatResponse:
            requests.append(request)
            queries = ", ".join(f'{{"issue": "{n}", "query": "truy vấn {n}"}}' for n in range(6))
            return ChatResponse(f'{{"issues": [{queries}]}}', "model", None, None, None)

    issues = decompose_question("Câu hỏi?", Chat(), date(2026, 3, 15), max_issues=3)

    assert [issue.query for issue in issues] == ["truy vấn 0", "truy vấn 1", "truy vấn 2"]
    assert requests[0].messages[1].content.startswith("Ngày áp dụng: 15/03/2026.")
    assert requests[0].temperature == 0.0


def _result(chunk_id: str) -> SimpleNamespace:
    return SimpleNamespace(chunk=SimpleNamespace(id=chunk_id))
