"""Add the Ministry of Finance's expiry dates to the repeal list.

    python scripts/add_ministry_expiry.py

Offline. Reads repeals/corpus-v1.json, corpus/mof-status.json, and the corpus manifest;
writes repeals/corpus-v1-ministry.json. An expiry date from year 2900 is a placeholder.
"""

import json
from pathlib import Path

from taxlens.retrieval.repeals import normalize

REPEALS = Path("data/evaluation/repeals/corpus-v1.json")
STATUS = Path("data/evaluation/corpus/mof-status.json")
MANIFEST = Path("data/evaluation/corpus/corpus-v1.json")
OUTPUT = Path("data/evaluation/repeals/corpus-v1-ministry.json")
EXPIRED = "Hết hiệu lực"


def main() -> None:
    stored = json.loads(REPEALS.read_text(encoding="utf-8"))
    repeals = dict(stored["repeals"])
    status = {
        normalize(number): record
        for number, record in json.loads(STATUS.read_text(encoding="utf-8"))["records"].items()
    }
    versions = json.loads(MANIFEST.read_text(encoding="utf-8"))["versions"]
    added = earlier = 0
    for number in sorted({version["document_number"] for version in versions}):
        record = status.get(normalize(number))
        if not record or record["status"] != EXPIRED or not record["expires"]:
            continue
        ended_on = record["expires"][:10]
        if int(ended_on[:4]) >= 2900:
            continue
        current = repeals.get(number)
        if current is None:
            repeals[number] = {"ended_on": ended_on, "rule": "ministry", "by": "ministry status"}
            added += 1
        else:
            # The ministry's record stands in for an inference it confirms.
            inferred = current["rule"] in ("guidance", "amendment")
            if ended_on < current["ended_on"]:
                earlier += 1
            if inferred or ended_on < current["ended_on"]:
                repeals[number] = {
                    **current,
                    "rule": "ministry" if inferred else current["rule"],
                    "by": "ministry status" if inferred else current["by"],
                    "ended_on": min(ended_on, current["ended_on"]),
                }
    rules: dict[str, int] = {}
    for repeal in repeals.values():
        rules[repeal["rule"]] = rules.get(repeal["rule"], 0) + 1
    OUTPUT.write_text(
        json.dumps(
            {**stored, "ended_count": len(repeals), "rules": rules, "repeals": repeals},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("added", added, "dates moved earlier", earlier, "rules", rules)


if __name__ == "__main__":
    main()
