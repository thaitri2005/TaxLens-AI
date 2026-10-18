"""Measure OCR settings against a PDF that also has a clean digital text layer.

The text layer is the reference: each page is rendered, OCR'd with every configuration, and
compared word by word. ``wer`` counts any wrong word; ``wer_unaccented`` ignores
diacritics, so the gap between the two is the diacritic loss. Use a born-digital PDF (for
example the Government's 301/2026/NĐ-CP); a text layer that is itself OCR output is not a
valid reference.

    python scripts/benchmark_ocr.py --document-number 301/2026/NĐ-CP --pages 3
"""

import argparse
import json
import re
import time
import unicodedata

from sqlalchemy import select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.document_processing.ocr import ocr_pages
from taxlens.document_processing.process import _has_usable_text, extract_pages
from taxlens.legal_data.models import DocumentVersion, LegalDocument
from taxlens.retrieval.text import fold_vietnamese
from taxlens.storage.factory import get_object_storage

DEFAULT_CONFIGURATIONS = ("144:6", "300:6", "300:3", "300:4")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark OCR settings against a text layer")
    parser.add_argument("--document-number", required=True)
    parser.add_argument("--pages", type=int, default=3, help="Pages to compare (1-10)")
    parser.add_argument(
        "--configurations",
        nargs="+",
        default=list(DEFAULT_CONFIGURATIONS),
        help="DPI:page-segmentation-mode pairs, for example 300:3",
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.pages <= 10:
        parser.error("--pages must be between 1 and 10")

    with SessionLocal() as session:
        version = session.scalars(
            select(DocumentVersion)
            .join(LegalDocument)
            .where(LegalDocument.document_number == arguments.document_number)
            .order_by(DocumentVersion.created_at.desc())
        ).first()
        if version is None:
            parser.exit(1, f"Document not found: {arguments.document_number}\n")
        artifact_key = version.raw_artifact_key
    raw_content = get_object_storage().get_bytes(artifact_key)
    reference_pages = extract_pages(raw_content, artifact_key)
    indices = [
        index for index, page in enumerate(reference_pages) if _has_usable_text([page])
    ][: arguments.pages]
    if not indices:
        parser.exit(1, "The document has no usable text layer to compare against\n")

    settings = get_settings()
    rows = []
    for configuration in arguments.configurations:
        dpi, page_segmentation_mode = (int(part) for part in configuration.split(":"))
        started = time.perf_counter()
        recognized = ocr_pages(raw_content, settings, indices, dpi, page_segmentation_mode)
        seconds_per_page = (time.perf_counter() - started) / len(indices)
        reference = " ".join(reference_pages[index] for index in indices)
        hypothesis = " ".join(recognized[index] for index in indices)
        rows.append(
            {
                "dpi": dpi,
                "psm": page_segmentation_mode,
                "wer": round(word_error_rate(reference, hypothesis), 4),
                "wer_unaccented": round(
                    word_error_rate(fold_vietnamese(reference), fold_vietnamese(hypothesis)), 4
                ),
                "seconds_per_page": round(seconds_per_page, 1),
            }
        )

    print(f"OCR benchmark: {arguments.document_number}, pages {[i + 1 for i in indices]}")
    print(f"{'dpi':>5} {'psm':>4} {'wer':>7} {'wer_unaccented':>15} {'sec/page':>9}")
    for row in rows:
        print(
            f"{row['dpi']:>5} {row['psm']:>4} {row['wer']:>7.2%} "
            f"{row['wer_unaccented']:>15.2%} {row['seconds_per_page']:>9}"
        )
    best = min(rows, key=lambda row: (row["wer"], row["seconds_per_page"]))
    print(f"Lowest word error rate: OCR_DPI={best['dpi']} OCR_PAGE_SEGMENTATION_MODE={best['psm']}")
    print(json.dumps(rows, ensure_ascii=False))


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level edit distance divided by the reference length."""

    expected = _words(reference)
    actual = _words(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for row, expected_word in enumerate(expected, start=1):
        current = [row]
        for column, actual_word in enumerate(actual, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (expected_word != actual_word),
                )
            )
        previous = current
    return previous[-1] / len(expected)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())


if __name__ == "__main__":
    main()
