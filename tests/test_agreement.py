from datetime import date

import pytest

from taxlens.evaluation.agreement import annotator_agreement, cohen_kappa
from taxlens.evaluation.gold_set import GoldCase, parse_provisions


def test_cohen_kappa_matches_a_hand_computed_value() -> None:
    # observed 0.75; chance (2*3 + 2*1) / 16 = 0.5; kappa (0.75 - 0.5) / 0.5
    labels = [("E", "E"), ("E", "S"), ("S", "S"), ("S", "S")]

    assert cohen_kappa(labels) == pytest.approx(0.5)
    assert cohen_kappa([("E", "E"), ("E", "E")]) is None
    assert cohen_kappa([]) is None


def test_agreement_matches_provisions_written_with_short_or_full_numbers() -> None:
    first = [
        _case("A1", "E: VAT Law 48/2024 Art 9(3) | S: Decree 181/2025 Art 26"),
        _case("A2", "E: Decree 181/2025 Art 4(1)"),
        _case("A3", "E: Decree 181/2025 Art 16(2)"),
    ]
    second = [
        _case("A1", "E: VAT Law 48/2024/QH15 Art 9(3) | E: Decree 181/2025 Art 26"),
        _case("A2", "E: Decree 181/2025 Art 4(1) | S: Circular 84/2025/TT-BNNMT Art 20"),
    ]

    agreement = annotator_agreement(first, second)

    assert agreement.case_count == 2
    assert agreement.item_count == 4
    assert agreement.observed == pytest.approx(0.5)
    assert agreement.essential_set_match_rate == pytest.approx(0.5)
    assert agreement.confusion == {("E", "E"): 2, ("S", "E"): 1, ("-", "S"): 1}
    assert [item["provision"] for item in agreement.disagreements] == [
        "decree 181/2025 Art 26",
        "circular 84/2025 Art 20",
    ]


def _case(case_id: str, provisions_text: str) -> GoldCase:
    provisions, unparsed = parse_provisions(provisions_text)
    return GoldCase(
        case_id=case_id,
        case_type="answerable",
        derived_from=None,
        question="?",
        as_of_date=date(2026, 3, 15),
        source_verified=True,
        uncertain=False,
        provisions=provisions,
        unparsed=unparsed,
    )
