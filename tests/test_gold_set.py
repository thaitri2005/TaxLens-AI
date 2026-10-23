from datetime import date
from pathlib import Path

from taxlens.evaluation.gold_set import (
    load_gold_set,
    parse_provisions,
    resolve_document_number,
)


def test_parse_provisions_reads_labels_articles_and_clauses() -> None:
    provisions, unparsed = parse_provisions(
        "E: VAT Law 48/2024 Art 5(1), as amended by Law 149/2025 Art 1(1)(a)"
        " | E: Decree 181/2025 Art 4(1) (+ clause 1b added by Decree 359/2025)"
        " | E: Circular 84/2025/TT-BNNMT Art 20(1)(c) | S: Decree 181/2025 Art 26"
    )

    assert unparsed == ()
    assert [(p.label, p.kind, p.number, p.article, p.clause) for p in provisions] == [
        ("E", "law", "48/2024", "5", "1"),
        ("E", "decree", "181/2025", "4", "1"),
        ("E", "circular", "84/2025/TT-BNNMT", "20", "1"),
        ("S", "decree", "181/2025", "26", None),
    ]


def test_parse_provisions_completes_numbers_from_earlier_items() -> None:
    provisions, unparsed = parse_provisions(
        "E: VAT Law 48/2024 Art 9(3) | S: VAT Law Art 9(2)(d) | E: Decree 181/2025 Art 4"
        " | S: Decree 181 Art 4 clause 1b | E: Livestock Law Art 2(2) | (none)"
    )

    assert [(p.number, p.article, p.clause) for p in provisions] == [
        ("48/2024", "9", "3"),
        ("48/2024", "9", "2"),
        ("181/2025", "4", None),
        ("181/2025", "4", "1b"),
    ]
    assert unparsed == ("E: Livestock Law Art 2(2)",)


def test_resolve_document_number_uses_the_matching_corpus_document() -> None:
    (law, decree, circular), _ = parse_provisions(
        "E: VAT Law 48/2024 Art 9 | E: Decree 181/2025 Art 4 | E: Circular 80/2021 Art 40"
    )
    corpus = ["48/2024/QH15", "48/2024/NĐ-CP", "181/2025/NĐ-CP"]

    assert resolve_document_number(law, corpus) == "48/2024/QH15"
    assert resolve_document_number(decree, corpus) == "181/2025/NĐ-CP"
    assert resolve_document_number(circular, corpus) == "80/2021/TT-BTC"


def test_gold_set_cases_score_only_essential_provisions(tmp_path: Path) -> None:
    path = tmp_path / "gold.csv"
    path.write_text(
        "case_id,case_type,derived_from,source,source_verified,as_of_date,filing_date,"
        "question,gold_answer,gold_provisions,uncertain,notes\n"
        'A1,answerable,,letter,Y,15/03/2026,,"Câu hỏi?",answer,'
        '"E: VAT Law 48/2024 Art 9(3) | S: Decree 181/2025 Art 26",N,\n'
        "R1,conditional,,letter,-,15/03/2026,,Câu hỏi khác?,answer,(none),N,\n",
        encoding="utf-8-sig",
    )

    answerable, conditional = load_gold_set(path)
    case = answerable.to_evaluation_case(["48/2024/QH15", "181/2025/NĐ-CP"])

    assert answerable.as_of_date == date(2026, 3, 15)
    assert not conditional.answerable
    assert case["relevant_document_numbers"] == ["48/2024/QH15"]
    assert case["relevant_articles"] == {"48/2024/QH15": ["9"]}
    assert case["relevant_clauses"] == {"48/2024/QH15": [["9", "3"]]}
    assert case["supporting_document_numbers"] == ["181/2025/NĐ-CP"]


def test_bundled_gold_set_parses() -> None:
    cases = load_gold_set(Path("data/evaluation/gold_set_v1.csv"))

    assert len({case.case_id for case in cases}) == len(cases)
    assert all(
        case.essential or case.case_type in {"conditional", "false premise"} for case in cases
    )
