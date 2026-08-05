from typing import Any

from taxlens.config import Settings


def ocr_pages(raw_content: bytes, settings: Settings) -> list[str]:
    if not settings.ocr_enabled:
        raise RuntimeError("Tesseract OCR is disabled")

    try:
        import pypdfium2  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("Tesseract OCR dependencies are unavailable") from error

    try:
        document: Any = pypdfium2.PdfDocument(raw_content)
        pages: list[str] = []
        total_pages = len(document)
        print(f"Tesseract OCR started: {total_pages} page(s)", flush=True)
        for index in range(total_pages):
            print(f"Tesseract OCR page {index + 1}/{total_pages}...", flush=True)
            page = document[index]
            bitmap = page.render(scale=settings.ocr_render_scale)
            image = bitmap.to_pil()
            pages.append(
                pytesseract.image_to_string(
                    image,
                    lang=settings.ocr_language,
                    config="--psm 6",
                    timeout=settings.ocr_timeout_seconds,
                )
            )
            image.close()
            bitmap.close()
            page.close()
        document.close()
        print("Tesseract OCR finished", flush=True)
        return pages
    except Exception as error:
        raise RuntimeError(f"Tesseract OCR failed: {error}") from error
