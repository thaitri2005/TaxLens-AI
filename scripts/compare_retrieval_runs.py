"""Compare two saved retrieval reports case by case (evaluate_tax_retrieval.py --output).

    python scripts/compare_retrieval_runs.py data/evaluation/runs/hybrid-asof.json \
        data/evaluation/runs/issue-guided-asof.json --ks 5 10 20

Refuses reports made on different frozen corpora or datasets.
"""

import argparse
import json
from pathlib import Path

from taxlens.evaluation.comparison import compare_runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", type=Path)
    parser.add_argument("method", type=Path)
    parser.add_argument("--ks", nargs="+", type=int, default=[5, 10, 20])
    arguments = parser.parse_args()

    baseline = json.loads(arguments.baseline.read_text(encoding="utf-8"))
    method = json.loads(arguments.method.read_text(encoding="utf-8"))
    for field in ("dataset_hash", "frozen_corpus", "as_of_filter"):
        if baseline.get(field) != method.get(field):
            parser.error(f"The reports differ in {field}: not a paired comparison")
    missing = [k for k in arguments.ks if str(k) not in method["metrics_by_k"]]
    if missing or any(str(k) not in baseline["metrics_by_k"] for k in arguments.ks):
        parser.error(f"Both reports need K = {arguments.ks}; rerun with --ks")

    summary = []
    for k in arguments.ks:
        comparison = compare_runs(baseline["cases"], method["cases"], k)
        summary.append(
            {
                **{key: value for key, value in comparison.items() if key != "cases"},
                "baseline_full_coverage": baseline["metrics_by_k"][str(k)].get(
                    "essential_in_corpus_full_coverage_rate"
                ),
                "method_full_coverage": method["metrics_by_k"][str(k)].get(
                    "essential_in_corpus_full_coverage_rate"
                ),
                "cases": comparison["cases"],
            }
        )
    print(
        json.dumps(
            {
                "baseline": baseline.get("retrieval_mode"),
                "method": method.get("retrieval_mode"),
                "by_k": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
