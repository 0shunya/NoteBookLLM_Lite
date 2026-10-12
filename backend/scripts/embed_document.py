import argparse

from app.db.database import SessionLocal
from app.services.embedding_indexer import embed_document_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Create embeddings for a stored document.")
    parser.add_argument("document_id", help="ID returned by the upload API")
    document_id = parser.parse_args().document_id
    db = SessionLocal()

    try:
        count = embed_document_chunks(
            db=db,
            document_id=document_id,
        )

        print(f"Embeddings created: {count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
