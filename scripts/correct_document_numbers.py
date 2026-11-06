"""Move documents stored under a wrong number to the right one, from a reviewed list.

Passages and embeddings stay as they are: they belong to the version, which only changes owner.
A dry run unless --apply is given. Safe to repeat: corrections already made are skipped.
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxlens.db import SessionLocal
from taxlens.legal_data.document_numbers import issuing_agency_for
from taxlens.legal_data.models import (
    DocumentVersion,
    LegalDocument,
    ProcessingJob,
    SourceRecord,
)

CORRECTIONS = Path("data/evaluation/corpus/number-corrections-v2.json")


def correct(session: Session, correction: dict[str, str]) -> str:
    old = session.scalar(
        select(LegalDocument).where(LegalDocument.document_number == correction["from"])
    )
    if old is None:
        return "already done"
    query = select(DocumentVersion).where(DocumentVersion.document_id == old.id)
    if "from_source" in correction:
        query = query.join(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id).where(
            SourceRecord.source_url.contains(correction["from_source"])
        )
    versions = list(session.scalars(query))
    if not versions:
        return "already done"

    target = session.scalar(
        select(LegalDocument).where(LegalDocument.document_number == correction["to"])
    )
    outcome = "added to existing document" if target else "renumbered"
    if target is None:
        target = LegalDocument(
            document_number=correction["to"],
            title=old.title,
            document_type=correction["to"].rsplit("/", 1)[-1],
            issuing_agency=issuing_agency_for(correction["to"]) or old.issuing_agency,
        )
        session.add(target)
        session.flush()
    for version in versions:
        version.document_id = target.id
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.document_version_id == version.id)
        )
        if job is not None and job.error_code == "DOCUMENT_NUMBER_MISMATCH":
            job.error_code = None
            job.error_detail = None
    session.flush()
    remaining = session.scalar(
        select(func.count())
        .select_from(DocumentVersion)
        .where(DocumentVersion.document_id == old.id)
    )
    if not remaining:
        session.delete(old)
        session.flush()
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Save the corrections")
    arguments = parser.parse_args()
    data = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    with SessionLocal() as session:
        for correction in data["wrong_document"] + data["written_differently"]:
            outcome = correct(session, correction)
            print(f"{correction['from']} -> {correction['to']}: {outcome}", flush=True)
        if arguments.apply:
            session.commit()
            print("Saved.")
        else:
            session.rollback()
            print("Dry run: nothing saved.")


if __name__ == "__main__":
    main()
