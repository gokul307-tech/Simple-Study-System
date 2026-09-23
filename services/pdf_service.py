from __future__ import annotations

from io import BytesIO


def extract_pdf(uploaded_file) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(uploaded_file.getvalue()))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text: raise ValueError("This PDF has no extractable text; scanned PDFs need OCR.")
        return text
    except ImportError as exc:
        raise ValueError("PDF support requires the pypdf package.") from exc
