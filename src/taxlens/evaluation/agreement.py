"""Agreement between two annotators of the gold set (docs/annotation-guideline.md).

Each annotator labels a case's provisions essential (E) or supporting (S). Over the
provisions either annotator listed, a provision's label is E, S, or absent ("-"), and
Cohen's kappa measures agreement on those labels beyond chance. The E/S decision is the
subjective part of the guideline, so it is what the score is about.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from taxlens.evaluation.gold_set import GoldCase, Provision

ABSENT = "-"


@dataclass(frozen=True)
class Agreement:
    case_count: int
    item_count: int
    observed: float
    kappa: float | None
    essential_set_match_rate: float
    # (first annotator's label, second's) -> count, over every provision either listed.
    confusion: dict[tuple[str, str], int]
    disagreements: list[dict[str, str]]


def annotator_agreement(first: Sequence[GoldCase], second: Sequence[GoldCase]) -> Agreement:
    """Agreement on the cases both annotators labelled, matched by ``case_id``."""

    second_by_id = {case.case_id: case for case in second}
    pairs = [(case, second_by_id[case.case_id]) for case in first if case.case_id in second_by_id]
    labels: list[tuple[str, str]] = []
    disagreements: list[dict[str, str]] = []
    essential_matches = 0
    for case_a, case_b in pairs:
        labels_a, labels_b = _labels(case_a), _labels(case_b)
        if {key for key, label in labels_a.items() if label == "E"} == {
            key for key, label in labels_b.items() if label == "E"
        }:
            essential_matches += 1
        for key in sorted(labels_a.keys() | labels_b.keys()):
            pair = (labels_a.get(key, ABSENT), labels_b.get(key, ABSENT))
            labels.append(pair)
            if pair[0] != pair[1]:
                disagreements.append(
                    {
                        "case_id": case_a.case_id,
                        "provision": _describe(key),
                        "first": pair[0],
                        "second": pair[1],
                    }
                )
    observed = sum(a == b for a, b in labels) / len(labels) if labels else 0.0
    return Agreement(
        case_count=len(pairs),
        item_count=len(labels),
        observed=observed,
        kappa=cohen_kappa(labels),
        essential_set_match_rate=essential_matches / len(pairs) if pairs else 0.0,
        confusion=dict(Counter(labels)),
        disagreements=disagreements,
    )


def cohen_kappa(labels: Sequence[tuple[str, str]]) -> float | None:
    """Cohen's kappa for paired labels; None when chance agreement is already total."""

    if not labels:
        return None
    count = len(labels)
    observed = sum(a == b for a, b in labels) / count
    first = Counter(a for a, _ in labels)
    second = Counter(b for _, b in labels)
    expected = sum(first[label] * second[label] for label in first) / count**2
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def _labels(case: GoldCase) -> dict[tuple[str, str, str, str | None], str]:
    labels: dict[tuple[str, str, str, str | None], str] = {}
    for provision in case.provisions:
        key = _key(provision)
        # Listed twice with different labels: E wins, as it would when scoring.
        if labels.get(key) != "E":
            labels[key] = provision.label
    return labels


def _key(provision: Provision) -> tuple[str, str, str, str | None]:
    # "48/2024" and "48/2024/QH15" are the same law; annotators may write either.
    number = "/".join(provision.number.split("/")[:2])
    return (provision.kind, number, provision.article, provision.clause)


def _describe(key: tuple[str, str, str, str | None]) -> str:
    kind, number, article, clause = key
    return f"{kind} {number} Art {article}" + (f"({clause})" if clause else "")
