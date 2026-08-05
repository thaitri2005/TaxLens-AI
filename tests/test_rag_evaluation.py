from taxlens.evaluation.rag import evaluate_rag_answer
from taxlens.intelligence.qa import CitedClaim


def test_rag_metrics_are_deterministic_and_citation_aware() -> None:
    metrics = evaluate_rag_answer(
        "thuế giá trị gia tăng",
        "Quy định về thuế giá trị gia tăng.",
        [CitedClaim(text="Quy định", citation_numbers=(1,))],
        ["Quy định về thuế giá trị gia tăng."],
        citation_count=1,
    )

    assert metrics.faithfulness == 1.0
    assert metrics.citation_completeness == 1.0
    assert metrics.answer_relevancy > 0
    assert metrics.context_precision == 1.0


def test_rag_metrics_do_not_reward_missing_answers() -> None:
    metrics = evaluate_rag_answer("thuế", None, [], [], citation_count=0)

    assert metrics.faithfulness == 0.0
    assert metrics.citation_completeness == 0.0
