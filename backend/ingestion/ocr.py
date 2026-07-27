from pathlib import Path
import pytesseract
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

# Ensure Tesseract is found on Windows default path
_tesseract_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if _tesseract_path.exists():
    pytesseract.pytesseract.tesseract_cmd = str(_tesseract_path)


def extract_text_from_image(
    image_data: bytes | str | Path,
    lang: str = "spa+eng",
) -> str:
    """Extract text from an image file path or bytes using Tesseract OCR."""
    if isinstance(image_data, (str, Path)):
        img = Image.open(str(image_data))
    else:
        img = Image.open(io.BytesIO(image_data))
    text: str = pytesseract.image_to_string(img, lang=lang)
    return text.strip()


def extract_text_from_scanned_pdf(
    pdf_path: str | Path,
    lang: str = "spa+eng",
    dpi: int = 300,
) -> str:
    """Convert scanned PDF pages to images and run OCR on each page.

    Requires PyMuPDF (fitz) to render pages as pixmaps.
    """
    import fitz

    pdf_path = Path(pdf_path)
    pages_text: list[str] = []

    with fitz.open(str(pdf_path)) as doc:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            text = extract_text_from_image(img_bytes, lang=lang)
            if text:
                pages_text.append(f"--- Página {page_num + 1} ---\n{text}")

    return "\n\n".join(pages_text)
