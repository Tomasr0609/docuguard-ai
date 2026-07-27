from pathlib import Path
from typing import Any
import logging

import pdfplumber
import fitz

logger = logging.getLogger(__name__)


def extract_text_from_native_pdf(pdf_path: str | Path) -> str:
    """Extract text directly from a native (text-based) PDF using pdfplumber."""
    pdf_path = Path(pdf_path)
    pages: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                pages.append(f"--- Página {i} ---\n{text.strip()}")

    return "\n\n".join(pages)


def extract_tables_from_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract tables from a PDF using pdfplumber."""
    pdf_path = Path(pdf_path)
    results: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table in tables:
                if table:
                    results.append({
                        "page": i,
                        "data": table,
                    })

    return results


def get_page_count(pdf_path: str | Path) -> int:
    """Get the total page count of a PDF using PyMuPDF."""
    pdf_path = Path(pdf_path)
    with fitz.open(str(pdf_path)) as doc:
        return len(doc)


def is_scanned_pdf(pdf_path: str | Path) -> bool:
    """Heuristic: if text extraction yields < 50 chars, it's likely scanned."""
    text = extract_text_from_native_pdf(pdf_path)
    return len(text.strip()) < 50
