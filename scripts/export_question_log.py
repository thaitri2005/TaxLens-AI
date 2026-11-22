"""Write the questions asked on the site to a CSV, as candidates for the gold set.

    python scripts/export_question_log.py --output question-log.csv [--since 2026-11-01] [--all]

By default only answers worth reviewing are listed: rated ones, and those the site refused
or failed. Usernames are left out; the CSV holds questions, answers, and ratings only. See
docs/annotation-guideline.md for turning a row into a gold case.
"""

import argparse
import csv
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import or_, select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import QuestionLog

COLUMNS = (
    "asked_at",
    "question",
    "status",
    "evidence_status",
    "rating",
    "comment",
    "cited_documents",
    "seconds",
    "answer",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since", type=date.fromisoformat, help="Only questions from this day")
    parser.add_argument(
        "--all", action="store_true", help="Every question, not only those to review"
    )
    arguments = parser.parse_args()

    statement = select(QuestionLog).order_by(QuestionLog.created_at)
    if arguments.since:
        statement = statement.where(
            QuestionLog.created_at >= datetime.combine(arguments.since, datetime.min.time())
        )
    if not arguments.all:
        statement = statement.where(
            or_(QuestionLog.rating.is_not(None), QuestionLog.status != "ANSWERED")
        )
    with SessionLocal() as session:
        entries = session.scalars(statement).all()
    with arguments.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for entry in entries:
            writer.writerow(
                [
                    entry.created_at.isoformat(timespec="minutes"),
                    entry.question,
                    entry.status,
                    entry.evidence_status,
                    {1: "up", -1: "down"}.get(entry.rating or 0, ""),
                    entry.comment or "",
                    "; ".join(entry.cited_documents),
                    entry.seconds,
                    entry.answer or "",
                ]
            )
    print(f"{len(entries)} questions written to {arguments.output}")


if __name__ == "__main__":
    main()
