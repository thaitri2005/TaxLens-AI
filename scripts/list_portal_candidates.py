"""List rule C2, C3, and C4 candidates from the government portal (docs/corpus-inclusion.md).

    python scripts/list_portal_candidates.py --output data/evaluation/corpus/candidates-v2.json

Metadata only: nothing is downloaded or stored in the database. A search shows at most 50
results, so narrower keyword searches replace the portal's category filter, and any search
still at the cap is recorded under ``capped`` as a possible silent loss, and one that keeps
timing out under ``failed``. About 25 minutes at one request every 2 seconds. Progress is
saved after each year or document, and running again skips what is already done.
"""

import argparse
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from taxlens.ingestion.connectors import GovernmentPortalSearch, SourceDocument, is_tax_title
from taxlens.retrieval.repeals import normalize

FIRST_YEAR, LAST_YEAR = 1992, 2026
ASSEMBLY, GOVERNMENT, FINANCE = "1", "2", "8"
TAX_KEYWORDS = ("thuế", "hóa đơn", "lệ phí", "hải quan", "kế toán")
NORMATIVE = re.compile(r"/(?:qh\d+|nd-cp|tt-[a-z]+|ttlt-[a-z-]+)$")
# Used only for a year whose laws reach the result cap.
LAW_KEYWORDS = (
    "Luật sửa đổi",
    "Luật Thuế",
    "Luật Quản lý",
    "Luật Bảo",
    "Luật Phòng",
    "Luật Công",
    "Luật Đầu tư",
    "Luật Tổ chức",
    "Luật Dân",
    "Luật Giáo",
    "Luật Khoa",
    "Luật An",
    "Luật Cán",
    "Luật Xây",
    "Luật Nhà",
    "Luật Đất",
    "Luật Y",
    "Luật Dược",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cited", type=Path, default=Path("data/evaluation/corpus/c3-candidates.json")
    )
    arguments = parser.parse_args()

    portal = GovernmentPortalSearch()
    saved = (
        json.loads(arguments.output.read_text(encoding="utf-8"))
        if arguments.output.exists()
        else {}
    )
    found: dict[str, dict[str, dict]] = {rule: saved.get(rule, {}) for rule in ("C4", "C2", "C3")}
    capped: list[str] = saved.get("capped", [])
    missing: list[str] = saved.get("cited_not_on_portal", [])
    failed: list[str] = []
    done: set[str] = set(saved.get("done", []))

    def save() -> None:
        arguments.output.write_text(
            json.dumps(
                {
                    "counts": {rule: len(items) for rule, items in found.items()},
                    "capped": capped,
                    "failed": failed,
                    "done": sorted(done),
                    "cited_not_on_portal": missing,
                    **found,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )

    def search(year: str, issuer: str, keyword: str) -> list[SourceDocument]:
        name = f"{year}/{issuer}/{keyword}"
        rows, at_cap = _post_with_retries(portal, year, issuer, keyword)
        if rows is None:
            failed.append(name)
            return []
        if at_cap:
            capped.append(name)
        return rows

    def keep_laws(rows: list[SourceDocument]) -> None:
        for row in rows:
            if "/QH" in row.document_number and normalize(row.title).startswith("luat "):
                found["C4"][row.document_number] = asdict(row)

    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        if f"C4/{year}" in done:
            continue
        before = len(capped)
        keep_laws(search(str(year), ASSEMBLY, "Luật"))
        if len(capped) > before:
            for keyword in LAW_KEYWORDS:
                keep_laws(search(str(year), ASSEMBLY, keyword))
        done.add(f"C4/{year}")
        save()

    for year in range(2000, LAST_YEAR + 1):
        if f"C2/{year}" in done:
            continue
        for issuer in (GOVERNMENT, FINANCE):
            for keyword in TAX_KEYWORDS:
                for row in search(str(year), issuer, keyword):
                    if NORMATIVE.search(normalize(row.document_number)) and is_tax_title(
                        row.title, row.document_number
                    ):
                        found["C2"][row.document_number] = asdict(row)
        done.add(f"C2/{year}")
        save()

    cited = json.loads(arguments.cited.read_text(encoding="utf-8"))["candidates"]
    for number in cited:
        if f"C3/{number}" in done:
            continue
        rows, _ = _post_with_retries(portal, "0", "0", number.upper())
        if rows is None:
            failed.append(f"C3/{number}")
            continue
        match = next((row for row in rows if normalize(row.document_number) == number), None)
        if match:
            found["C3"][match.document_number] = asdict(match)
        else:
            missing.append(number)
        done.add(f"C3/{number}")
        save()
    print(
        found["C4"].__len__(),
        found["C2"].__len__(),
        found["C3"].__len__(),
        len(missing),
        len(capped),
    )


def _post_with_retries(
    portal: GovernmentPortalSearch, year: str, issuer: str, keyword: str
) -> tuple[list[SourceDocument] | None, bool]:
    for attempt in range(1, 4):
        try:
            return portal._post(category="0", year=year, issuer=issuer, keyword=keyword)
        except httpx.HTTPError:
            time.sleep(10 * attempt)
    return None, False


if __name__ == "__main__":
    main()
