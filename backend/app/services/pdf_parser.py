"""Page-aware text extraction for text-based PDF documents."""

from dataclasses import dataclass

from pypdf import PdfReader

from app.services.chunker import create_chunks


@dataclass(frozen=True)
class PdfExtraction:
    page_count: int
    chunks: list[dict]
    warnings: list[str]


def extract_document(file_path: str, document_id: str) -> PdfExtraction:
    reader = PdfReader(file_path, strict=False)
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise ValueError("Password-protected PDFs are not supported.")
        except Exception as exc:
            raise ValueError("Password-protected PDFs are not supported.") from exc

    page_count = len(reader.pages)
    all_chunks: list[dict] = []
    blank_pages: list[int] = []

    for page_number, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        text = "\n".join(line.strip() for line in raw_text.replace("\x00", "").splitlines())
        text = "\n\n".join(block for block in text.split("\n\n") if block.strip())
        if len(text.strip()) < 20:
            blank_pages.append(page_number)
            continue

        all_chunks.extend(
            create_chunks(text=text, page_number=page_number, document_id=document_id)
        )

    warnings = []
    if blank_pages:
        page_list = ", ".join(str(page) for page in blank_pages)
        warnings.append(
            f"No readable text was extracted from page(s) {page_list}; scanned pages need OCR."
        )

    return PdfExtraction(page_count=page_count, chunks=all_chunks, warnings=warnings)


def extract_pages(file_path: str, document_id: str) -> list[dict]:
    """Backward-compatible helper returning extracted chunks only."""
    return extract_document(file_path, document_id).chunks
