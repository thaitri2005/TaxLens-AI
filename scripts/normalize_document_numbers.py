"""Remove typing slips from stored document numbers ("219/2013/TT- BTC" -> "219/2013/TT-BTC").

    python scripts/normalize_document_numbers.py           # list the changes
    python scripts/normalize_document_numbers.py --apply

A number whose corrected form already belongs to another document is listed and left
alone: the same document is then held twice, which is for a person to resolve.
"""

import argparse

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.document_numbers import canonical_document_number
from taxlens.legal_data.models import LegalDocument


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Write the changes")
    arguments = parser.parse_args()

    with SessionLocal() as session:
        documents = list(session.scalars(select(LegalDocument)))
        taken = {document.document_number for document in documents}
        renamed = duplicates = 0
        for document in documents:
            canonical = canonical_document_number(document.document_number)
            if canonical == document.document_number:
                continue
            if canonical in taken:
                duplicates += 1
                print(f"DUPLICATE  {document.document_number!r} -> {canonical!r} exists")
                continue
            print(f"rename     {document.document_number!r} -> {canonical!r}")
            taken.discard(document.document_number)
            taken.add(canonical)
            document.document_number = canonical
            renamed += 1
        if arguments.apply:
            session.commit()
    print(
        f"{renamed} renamed{'' if arguments.apply else ' (dry run; --apply to write)'}, "
        f"{duplicates} left as duplicates"
    )


if __name__ == "__main__":
    main()
