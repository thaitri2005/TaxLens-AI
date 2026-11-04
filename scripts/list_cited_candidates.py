"""List documents outside the corpus that tax documents cite (rule C3, docs/corpus-inclusion.md).

    python scripts/list_cited_candidates.py --output data/evaluation/corpus/c3-candidates.json

One pass over every passage. Counts, for each cited normative number, the different
documents citing it in operative text, leaving out documents listed as ended.
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.references import find_references
from taxlens.retrieval.repeals import ended_documents, normalize

NORMATIVE = re.compile(r"/(?:qh\d+|nd-cp|tt-[a-z]+|ttlt-[a-z-]+)$")
THRESHOLD = 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--repeals", type=Path, default=Path("data/evaluation/repeals/corpus-v1.json")
    )
    arguments = parser.parse_args()

    stored = json.loads(arguments.repeals.read_text(encoding="utf-8"))["repeals"]
    ended = set(ended_documents(stored, date.today()))
    citing: dict[str, set[str]] = defaultdict(set)
    with SessionLocal() as session:
        numbers = list(session.scalars(select(LegalDocument.document_number)))
        statement = (
            select(LegalDocument.document_number, DocumentChunk.content)
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
        )
        for number, content in session.execute(statement.execution_options(yield_per=2000)):
            if number in ended:
                continue
            for reference in find_references(content):
                cited = reference.document_number
                if cited and NORMATIVE.search(cited):
                    citing[cited].add(number)
    held = {normalize(number) for number in numbers}
    outside = {cited: sorted(by) for cited, by in citing.items() if cited not in held}
    counts = {n: sum(len(by) >= n for by in outside.values()) for n in (1, 2, 3)}
    candidates = {
        cited: {"citing_count": len(by), "citing": by[:5]}
        for cited, by in sorted(outside.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(by) >= THRESHOLD
    }
    arguments.output.write_text(
        json.dumps(
            {"threshold": THRESHOLD, "counts_at": counts, "candidates": candidates},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(counts)


if __name__ == "__main__":
    main()
