import pytest

from taxlens.evaluation.comparison import compare_runs, sign_test

RATE = ["48/2024/QH15", "9", "3"]
EXCEPTION = ["174/2025/NĐ-CP", "1", "1"]
GAP = ["84/2025/TT-BNNMT", "20", "1"]


def test_compare_runs_counts_wins_losses_and_ignores_corpus_gaps() -> None:
    baseline = [
        _case("A1", (RATE, 2), (EXCEPTION, None)),
        _case("A2", (RATE, 1), (GAP, None, False)),
        _case("A3", (RATE, 3), (EXCEPTION, 4)),
        {"case_id": "R1"},  # no essential provisions
    ]
    method = [
        _case("A1", (RATE, 1), (EXCEPTION, 5)),  # finds the exception too: win
        _case("A2", (RATE, 1), (GAP, None, False)),  # same; the gap does not count: tie
        _case("A3", (RATE, 12), (EXCEPTION, 2)),  # loses the rate at K = 10: loss
        {"case_id": "R1"},
    ]

    comparison = compare_runs(baseline, method, k=10)

    assert [row["outcome"] for row in comparison["cases"]] == ["win", "tie", "loss"]
    assert (comparison["wins"], comparison["losses"], comparison["ties"]) == (1, 1, 1)
    assert comparison["cases"][1]["in_corpus"] == 1


def test_sign_test_is_two_sided_and_exact() -> None:
    assert sign_test(0, 0) == 1.0
    assert sign_test(5, 0) == pytest.approx(2 / 32)
    assert sign_test(3, 3) == 1.0
    assert sign_test(8, 2) == pytest.approx(2 * (1 + 10 + 45) / 1024)


def _case(case_id: str, *ranks: tuple) -> dict:
    return {
        "case_id": case_id,
        "essential_provision_ranks": [
            {"provision": [place], "rank": item[1], "in_corpus": item[2] if len(item) > 2 else True}
            for item in ranks
            for place in [item[0]]
        ],
    }
