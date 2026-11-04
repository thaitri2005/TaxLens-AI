"""Look for the cited numbers still unresolved in the ministry database (rule C3).

    python scripts/resolve_cited_candidates.py

The ministry has no search by number, so this pages through its circulars, joint
circulars, and decrees (about 8,000 of 14,500 records; other types are not cited under
rule C3), about 40 minutes. A resumed run continues from the saved position. It also keeps
each record's status and expiry date in mof-status.json, to check the repeal rules against.
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

from taxlens.ingestion.mof import (
    BASE_URL,
    SEARCH_PATH,
    MofLegalDocumentConnector,
    _to_source_document,
)
from taxlens.retrieval.repeals import normalize

CANDIDATES = Path("data/evaluation/corpus/candidates-v2.json")
STATUS = Path("data/evaluation/corpus/mof-status.json")
TYPES = {"decree": 11, "joint circular": 21, "circular": 20}
PAGE_SIZE = 100


def main() -> None:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    connector = MofLegalDocumentConnector()
    saved = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    status = saved.get("records", {})
    position = saved.get("position", {})
    wanted = set(data["cited_not_on_portal"])
    started = time.monotonic()
    for label, type_id in TYPES.items():
        page = position.get(label, 0) + 1
        while True:
            payload = connector._request(
                "POST",
                BASE_URL + SEARCH_PATH,
                json={
                    "Page": page,
                    "PageSize": PAGE_SIZE,
                    "ContentType": "LegalDocument",
                    "ContentTypeId": 0,
                    "Field": {},
                    "Organization": {},
                    "Editor": {},
                    "DocumentStatus": {},
                    "DocumentType": {"id": type_id},
                    "DocumentTypeForbidden": {},
                },
            ).json()
            records = payload.get("documents") or []
            total = int(payload.get("totalItem") or 0)
            for record in records:
                number = str(record.get("no") or "")
                status[number] = {
                    "status": record.get("documentStatusRecordName"),
                    "expires": record.get("legalExpireDate"),
                    "applies": record.get("legalApplyDate"),
                }
                folded = normalize(number)
                if folded in wanted:
                    document = _to_source_document(record)
                    if document:
                        data["C3"][document.document_number] = asdict(document)
                        wanted.discard(folded)
            position[label] = page
            data["cited_not_on_portal"] = sorted(wanted)
            data["counts"] = {rule: len(data[rule]) for rule in ("C4", "C2", "C3")}
            CANDIDATES.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            STATUS.write_text(
                json.dumps({"position": position, "records": status}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(
                f"{label} page {page}/{-(-total // PAGE_SIZE)}; "
                f"{len(wanted)} unresolved; {round(time.monotonic() - started)} s",
                flush=True,
            )
            if len(records) < PAGE_SIZE or page * PAGE_SIZE >= total:
                break
            page += 1
            time.sleep(0.5)
    print("done;", len(wanted), "unresolved;", len(status), "records", flush=True)


if __name__ == "__main__":
    main()
