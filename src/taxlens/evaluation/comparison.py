"""Paired comparison of two retrieval runs on the same cases (docs/issue-guided-retrieval.md).

A case is a win for the method when, within the top K, it finds an essential provision the
baseline misses and misses none the baseline finds; a loss in the opposite case; anything
else is a tie. Only provisions held in the corpus count, since a corpus gap is not a
ranking result.
"""

from collections.abc import Mapping, Sequence
from math import comb
from typing import Any


def found_provisions(case_report: Mapping[str, Any], k: int) -> set[str]:
    """The essential provisions held in the corpus that this run found within K."""

    return {
        repr(item["provision"])
        for item in case_report.get("essential_provision_ranks", [])
        if item.get("in_corpus", True) and item["rank"] is not None and item["rank"] <= k
    }


def compare_runs(
    baseline: Sequence[Mapping[str, Any]], method: Sequence[Mapping[str, Any]], k: int
) -> dict[str, Any]:
    method_by_id = {case["case_id"]: case for case in method}
    rows = []
    for base_case in baseline:
        method_case = method_by_id.get(base_case["case_id"])
        if method_case is None or "essential_provision_ranks" not in base_case:
            continue
        base_found = found_provisions(base_case, k)
        method_found = found_provisions(method_case, k)
        gained, lost = method_found - base_found, base_found - method_found
        outcome = "win" if gained and not lost else "loss" if lost and not gained else "tie"
        rows.append(
            {
                "case_id": base_case["case_id"],
                "outcome": outcome,
                "baseline_found": len(base_found),
                "method_found": len(method_found),
                "in_corpus": sum(
                    item.get("in_corpus", True) for item in base_case["essential_provision_ranks"]
                ),
                "gained": sorted(gained),
                "lost": sorted(lost),
            }
        )
    wins = sum(row["outcome"] == "win" for row in rows)
    losses = sum(row["outcome"] == "loss" for row in rows)
    return {
        "k": k,
        "case_count": len(rows),
        "wins": wins,
        "losses": losses,
        "ties": len(rows) - wins - losses,
        "sign_test_p": sign_test(wins, losses),
        "cases": rows,
    }


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test: the chance of a split at least this uneven if both
    methods were equally likely to win a non-tied case."""

    trials = wins + losses
    if trials == 0:
        return 1.0
    tail = sum(comb(trials, count) for count in range(min(wins, losses) + 1)) / (1 << trials)
    return min(1.0, 2 * tail)
