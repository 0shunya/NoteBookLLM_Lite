from pypdf import PdfReader

from app.services.chunker import create_chunks


def extract_pages(
    file_path: str,
    document_id: str
) -> list[dict]:

    reader = PdfReader(file_path)

    all_chunks = []

    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):

        # Extract text from this page.
        raw_text = page.extract_text() or ""

        # Convert PDF line breaks and excessive whitespace
        # into normal readable text.
        text = " ".join(raw_text.split())

        # Turn the page text into retrieval-friendly chunks.
        page_chunks = create_chunks(
            text=text,
            page_number=page_number,
            document_id=document_id
        )

        all_chunks.extend(page_chunks)

    return all_chunks