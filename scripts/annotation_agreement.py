"""Agreement between two annotators' copies of the gold set.

    python scripts/annotation_agreement.py data/evaluation/gold_set_v1.csv \
        data/evaluation/gold_set_v1_annotator2.csv

The second file needs only the cases the second annotator labelled, in the same columns.
"""

import argparse
import json
from pathlib import Path

from taxlens.evaluation.agreement import annotator_agreement
from taxlens.evaluation.gold_set import load_gold_set


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("first", type=Path, help="The first annotator's gold set CSV")
    parser.add_argument("second", type=Path, help="The second annotator's gold set CSV")
    arguments = parser.parse_args()

    agreement = annotator_agreement(load_gold_set(arguments.first), load_gold_set(arguments.second))
    if not agreement.case_count:
        parser.error("The two files share no case_id")
    print(
        json.dumps(
            {
                "case_count": agreement.case_count,
                "provision_count": agreement.item_count,
                "observed_agreement": round(agreement.observed, 3),
                "cohen_kappa": None if agreement.kappa is None else round(agreement.kappa, 3),
                "essential_set_match_rate": round(agreement.essential_set_match_rate, 3),
                "confusion": {
                    f"{first} vs {second}": count
                    for (first, second), count in sorted(agreement.confusion.items())
                },
                "disagreements": agreement.disagreements,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
