"""Tesseract OCR for scanned PDF pages.

Vietnamese diacritics are small marks; Tesseract is trained for about 300 DPI, and the
earlier ~144 DPI rendering lost many of them ("hóa don"). Measured on 301/2026/NĐ-CP
(``scripts/benchmark_ocr.py``, 3 pages): 300 DPI cut word error rate from 31.7% to 25.6%;
page segmentation mode 6 (one text block) scored 25.6% against 26.0% for mode 3 and 30.1%
for mode 4, so mode 6 stays the default.
"""

from collections.abc import Sequence
from typing import Any

from taxlens.config import Settings

POINTS_PER_INCH = 72


def ocr_pages(
    raw_content: bytes,
    settings: Settings,
    page_indices: Sequence[int] | None = None,
    dpi: int | None = None,
    page_segmentation_mode: int | None = None,
) -> dict[int, str]:
    """OCR the given zero-based pages (all pages by default); returns text per page.

    A page that times out or fails is returned as empty text so one bad page does not
    discard a long document; the caller decides whether enough text remains.
    """

    if not settings.ocr_enabled:
        raise RuntimeError("Tesseract OCR is disabled")
    try:
        import pypdfium2  # type: ignore[import-untyped]
        import pytesseract  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("Tesseract OCR dependencies are unavailable") from error

    scale = (dpi or settings.ocr_dpi) / POINTS_PER_INCH
    config = f"--psm {page_segmentation_mode or settings.ocr_page_segmentation_mode}"
    try:
        document: Any = pypdfium2.PdfDocument(raw_content)
    except Exception as error:
        raise RuntimeError(f"PDF could not be opened for OCR: {error}") from error

    texts: dict[int, str] = {}
    try:
        indices = list(page_indices) if page_indices is not None else range(len(document))
        print(f"Tesseract OCR started: {len(indices)} page(s), {config}", flush=True)
        for position, index in enumerate(indices, start=1):
            page = document[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert("L")
            try:
                texts[index] = pytesseract.image_to_string(
                    image,
                    lang=settings.ocr_language,
                    config=config,
                    timeout=settings.ocr_timeout_seconds,
                )
            except RuntimeError as error:
                # pytesseract raises RuntimeError on timeout; keep the rest of the document.
                print(f"Tesseract OCR page {index + 1} failed: {error}", flush=True)
                texts[index] = ""
            finally:
                image.close()
                bitmap.close()
                page.close()
            if position % 10 == 0:
                print(f"Tesseract OCR {position}/{len(indices)} pages", flush=True)
    finally:
        document.close()
    print("Tesseract OCR finished", flush=True)
    return texts
