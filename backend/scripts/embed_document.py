from app.db.database import SessionLocal
from app.services.embedding_indexer import embed_document_chunks


DOCUMENT_ID = "76fa161f-ddee-4e16-b33f-42f26682f8f4"


def main():
    db = SessionLocal()

    try:
        count = embed_document_chunks(
            db=db,
            document_id=DOCUMENT_ID,
        )

        print(f"Embeddings created: {count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()