"""Decompose each gold-set question into legal issues, once, for issue-guided retrieval.

    python scripts/decompose_issues.py --dataset data/evaluation/gold_set_v1.csv \
        --output data/evaluation/issues/gold_set_v1.json

Questions already in the output file are kept, so the stored decompositions stay fixed
across runs; --refresh decomposes everything again. Needs HF_TOKEN, not the database.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from taxlens.config import get_settings
from taxlens.evaluation.gold_set import load_gold_set
from taxlens.intelligence.chat import ChatProviderError, get_chat_provider
from taxlens.retrieval.issues import PROMPT_VERSION, decompose_question


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/gold_set_v1.csv"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/evaluation/issues/gold_set_v1.json")
    )
    parser.add_argument("--refresh", action="store_true", help="Decompose every case again")
    arguments = parser.parse_args()

    stored = (
        json.loads(arguments.output.read_text(encoding="utf-8"))
        if arguments.output.is_file() and not arguments.refresh
        else {}
    )
    cases = stored.setdefault("cases", {})
    chat = get_chat_provider()
    model = get_settings().hf_chat_model
    failed = []
    for case in load_gold_set(arguments.dataset):
        key = question_key(case.question)
        done = cases.get(case.case_id, {})
        if done.get("question_hash") == key and done.get("prompt_version") == PROMPT_VERSION:
            continue
        try:
            issues = decompose_question(case.question, chat, case.as_of_date)
        except ChatProviderError as error:
            failed.append(case.case_id)
            print(f"{case.case_id}: FAILED ({error})")
            continue
        cases[case.case_id] = {
            "question_hash": key,
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "issues": [{"issue": issue.issue, "query": issue.query} for issue in issues],
        }
        print(f"{case.case_id}: {len(issues)} issue(s)")
        for issue in issues:
            print(f"    {issue.query}")

    stored["updated_at"] = datetime.now(UTC).isoformat()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failed:
        raise SystemExit(f"Not decomposed (run again to retry): {', '.join(failed)}")


def question_key(question: str) -> str:
    """Changes when a case's question is edited, so its decomposition is made again."""

    return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    main()
