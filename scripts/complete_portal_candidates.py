"""Narrow the portal searches that hit the result cap in candidates-v2.json.

    python scripts/complete_portal_candidates.py

Keywords come from the titles already listed, not from the gold set: for laws, the first
two words after "Luật" of every listed law; for tax searches, a fixed list of tax topics.
Adds to the file in place. About 200 requests, 7 minutes.
"""

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from list_portal_candidates import ASSEMBLY, NORMATIVE

from taxlens.ingestion.connectors import GovernmentPortalSearch, is_tax_title
from taxlens.retrieval.repeals import normalize

CANDIDATES = Path("data/evaluation/corpus/candidates-v2.json")
TAX_TOPICS = (
    "thuế giá trị gia tăng",
    "thuế thu nhập",
    "thuế xuất khẩu",
    "thuế nhập khẩu",
    "thuế tiêu thụ",
    "thuế tài nguyên",
    "thuế sử dụng",
    "hoàn thuế",
    "miễn thuế",
    "giảm thuế",
    "quản lý thuế",
    "thuế suất",
    "kê khai",
)
FEE_TOPICS = ("thu lệ phí", "mức thu", "lệ phí cấp", "lệ phí đăng ký")


def main() -> None:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    portal = GovernmentPortalSearch()
    still_capped: list[str] = []
    failed: list[str] = []

    def search(year: str, issuer: str, keyword: str) -> list:
        for attempt in range(1, 4):
            try:
                rows, at_cap = portal._post(category="0", year=year, issuer=issuer, keyword=keyword)
            except httpx.HTTPError:
                time.sleep(10 * attempt)
                continue
            if at_cap:
                still_capped.append(f"{year}/{issuer}/{keyword}")
            return rows
        failed.append(f"{year}/{issuer}/{keyword}")
        return []

    before = {rule: len(data[rule]) for rule in ("C2", "C4")}
    keywords = {
        " ".join(row["title"].split()[:3])
        for row in data["C4"].values()
        if row["title"].casefold().startswith("luật ")
    }
    for keyword in sorted(keywords):
        for row in search("2025", ASSEMBLY, keyword):
            if "/QH" in row.document_number and normalize(row.title).startswith("luat "):
                data["C4"][row.document_number] = asdict(row)

    remaining = [item for item in data["capped"] if not item.startswith("2025/")]
    remaining += data.get("failed", [])
    for item in remaining:
        year, issuer, keyword = item.split("/", 2)
        topics = FEE_TOPICS if keyword == "lệ phí" else TAX_TOPICS
        if keyword not in ("thuế", "lệ phí"):
            topics = (keyword,)
        for topic in topics:
            for row in search(year, issuer, topic):
                if NORMATIVE.search(normalize(row.document_number)) and is_tax_title(
                    row.title, row.document_number
                ):
                    data["C2"][row.document_number] = asdict(row)

    data["capped_before_narrowing"] = data["capped"]
    data["capped"] = still_capped
    data["failed"] = failed
    data["counts"] = {rule: len(data[rule]) for rule in ("C4", "C2", "C3")}
    CANDIDATES.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(before, data["counts"], "still capped", still_capped, "failed", failed)


if __name__ == "__main__":
    main()
