"""Answer the gold-set questions as the site does, and grade each answer against its gold answer.

    python scripts/grade_answers.py --output data/evaluation/runs/answers-gold-v1-NAME.json
    python scripts/grade_answers.py --regrade REPORT --output REPORT

Each case is answered by ``answer_question`` with the site's settings (5 passages, today's
ended documents left out), then a judge model from another family compares the answer with
the gold answer: ``correct``, ``partly``, ``wrong``, or ``refused`` (declined when an answer
was expected). The judge is a model, not a tax expert: read its reasons, and record where you
disagree in the case's ``review``. ``--regrade`` grades again only the cases a report left
``ungraded`` (the judge failed), without answering again. Answers cost about $0.002 each and
grades much less; run once per change.
"""

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.intelligence.chat import (
    ChatMessage,
    ChatProviderError,
    ChatRequest,
    HuggingFaceChatProvider,
    get_chat_provider,
)
from taxlens.intelligence.qa import answer_question
from taxlens.retrieval.embeddings import get_embedding_provider

VERDICTS = ("correct", "partly", "wrong", "refused")
JUDGE_INSTRUCTIONS = (
    "You grade answers of a Vietnamese tax-law assistant against a reference answer written "
    "by the evaluation's authors. Judge only whether the assistant's conclusion agrees with the "
    "reference; do not judge style, length, or citations. Verdicts:\n"
    "- correct: reaches the reference conclusion (or meets its PASS condition) and does not "
    "contradict it.\n"
    "- partly: right direction but misses a key element the reference requires, or hedges "
    "between the right conclusion and a wrong one.\n"
    "- wrong: contradicts the reference, or meets its FAIL condition.\n"
    "- refused: declines to answer when the reference expects an answer. A refusal that the "
    "reference asks for (for example, a document that cannot be verified) is correct.\n"
    'Return JSON only: {"verdict": "correct|partly|wrong|refused", "reason": "<one or two '
    'sentences in English>"}'
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/gold_set_v1.csv"))
    parser.add_argument("--judge-model", default="Qwen/Qwen3-235B-A22B-Instruct-2507")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--regrade", type=Path, help="A report whose ungraded cases to grade")
    parser.add_argument(
        "--cases-from", type=Path, help="Answer only the cases of this earlier report, to compare"
    )
    arguments = parser.parse_args()

    settings = get_settings()
    judge = HuggingFaceChatProvider(
        settings.model_copy(update={"hf_chat_model": arguments.judge_model})
    )
    if arguments.regrade:
        previous = json.loads(arguments.regrade.read_text(encoding="utf-8"))
        answer_model, reports = previous["answer_model"], previous["cases"]
        for report in reports:
            if report["verdict"] == "ungraded":
                report["verdict"], report["reason"] = _grade(judge, report)
                print(f"{report['case_id']}: {report['verdict']}", flush=True)
    else:
        only = None
        if arguments.cases_from:
            earlier = json.loads(arguments.cases_from.read_text(encoding="utf-8"))["cases"]
            only = {case["case_id"] for case in earlier}
        answer_model, reports = settings.hf_chat_model, _answer(arguments.dataset, only)
        for report in reports:
            report["verdict"], report["reason"] = _grade(judge, report)
            print(f"{report['case_id']}: {report['status']}, {report['verdict']}", flush=True)

    counted = [report for report in reports if not report["uncertain"]]
    summary = {verdict: sum(r["verdict"] == verdict for r in counted) for verdict in VERDICTS}
    output = {
        "answer_model": answer_model,
        "judge_model": arguments.judge_model,
        "dataset": str(arguments.dataset),
        "case_count": len(counted),
        "summary": summary,
        "note": "Cases marked uncertain are graded but left out of the summary.",
        "cases": reports,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("summary:", summary)


def _answer(dataset: Path, only: set[str] | None = None) -> list[dict[str, Any]]:
    """Each gold case (or those in ``only``) answered as the site answers it."""

    rows = [
        row
        for row in csv.DictReader(dataset.open(encoding="utf-8-sig"))
        if only is None or row["case_id"] in only
    ]
    embedding_provider = get_embedding_provider()
    reports: list[dict[str, Any]] = []
    with SessionLocal() as session:
        for row in rows:
            started = time.perf_counter()
            result = answer_question(
                session, row["question"], get_chat_provider(), embedding_provider, retrieval_limit=5
            )
            reports.append(
                {
                    "case_id": row["case_id"],
                    "case_type": row["case_type"],
                    "uncertain": row["uncertain"] == "Y",
                    "question": row["question"],
                    "gold_answer": row["gold_answer"],
                    "status": result.status.value,
                    "answer": result.answer,
                    "uncertainties": result.uncertainties,
                    "cited_documents": [citation.document_number for citation in result.citations],
                    "seconds": round(time.perf_counter() - started, 1),
                }
            )
    return reports


def _grade(judge: HuggingFaceChatProvider, report: dict[str, Any]) -> tuple[str, str]:
    content = (
        f"Question: {report['question']}\n\nReference answer: {report['gold_answer']}\n\n"
        f"Assistant status: {report['status']}\n"
        f"Assistant answer: {report['answer'] or '(no answer)'}\n"
        f"Assistant uncertainties: {'; '.join(report['uncertainties']) or 'none'}"
    )
    try:
        response = judge.complete(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=JUDGE_INSTRUCTIONS),
                    ChatMessage(role="user", content=content),
                ],
                max_output_tokens=300,
                temperature=0.0,
            )
        )
        payload = json.loads(
            response.content[response.content.find("{") : response.content.rfind("}") + 1]
        )
    except (ChatProviderError, ValueError) as error:
        return "ungraded", f"Judge failed: {error}"
    verdict = str(payload.get("verdict", "")).strip().lower()
    return (verdict if verdict in VERDICTS else "ungraded"), str(payload.get("reason", ""))


if __name__ == "__main__":
    main()
