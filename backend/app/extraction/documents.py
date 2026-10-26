"""Turn uploaded files into page texts. OCR is optional (needs Tesseract installed)."""

import importlib.util
import io
from functools import lru_cache

import pymupdf

MIN_TEXT_CHARS = 25


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    if importlib.util.find_spec("pytesseract") is None or importlib.util.find_spec("PIL") is None:
        return False
    try:
        import pytesseract

        pytesseract.get_tesseract_version()  # fails if the Tesseract program is not installed
        return True
    except Exception:
        return False


def _ocr_image_bytes(data: bytes) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return pytesseract.image_to_string(img)


def image_text(data: bytes) -> str:
    if not ocr_available():
        raise ValueError(
            "Reading photos needs Tesseract OCR. Install Tesseract and run "
            "'pip install pytesseract pillow', or upload a text PDF / type the bill instead."
        )
    return _ocr_image_bytes(data)


def pdf_pages(data: bytes) -> tuple[list[str], list[str]]:
    """Text of each page, OCR-ing scanned pages when possible. Returns (pages, warnings)."""
    warnings: list[str] = []
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not open the PDF: {exc}") from exc
    pages: list[str] = []
    scanned = 0
    with doc:
        if doc.needs_pass:
            raise ValueError("The PDF is password-protected. Remove the password and upload again.")
        for page in doc:
            text = page.get_text()
            if len(text.strip()) < MIN_TEXT_CHARS:
                if ocr_available():
                    text = _ocr_image_bytes(page.get_pixmap(dpi=200).tobytes("png"))
                else:
                    scanned += 1
            pages.append(text)
    if scanned:
        warnings.append(f"{scanned} page(s) look scanned and were skipped because OCR (Tesseract) is not installed.")
    return pages, warnings


def file_text(filename: str, data: bytes) -> tuple[list[str], list[str]]:
    """Pages of text from a PDF, image or text file."""
    name = filename.lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        return pdf_pages(data)
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
        return [image_text(data)], []
    try:
        return [data.decode("utf-8-sig")], []
    except UnicodeDecodeError:
        return [data.decode("latin-1")], []
