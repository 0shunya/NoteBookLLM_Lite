from app.db.database import SessionLocal
from app.services.hybrid_search import hybrid_search_chunks


DOCUMENT_IDS = [
    "385fee53-5bb4-4c3c-9479-4b35f47f5ee4",
    "af9aeef4-7d77-498e-a734-7ba234f0e713",
]


def main():
    db = SessionLocal()

    try:
        question = "What programming languages and technologies does Shlok know?"

        results = hybrid_search_chunks(
            db=db,
            query=question,
            document_ids=DOCUMENT_IDS,
            limit=5,
            candidate_limit=10,
        )

        print("\nMULTI-DOCUMENT SEARCH RESULTS")
        print("=" * 70)

        for index, result in enumerate(results, start=1):
            print(f"\nResult #{index}")
            print(f"Chunk ID:       {result['chunk_id']}")
            print(f"Document ID:    {result['document_id']}")
            print(f"Filename:       {result['filename']}")
            print(f"Page:           {result['page_number']}")
            print(f"Vector Rank:    {result['vector_rank']}")
            print(f"Keyword Rank:   {result['keyword_rank']}")
            print(f"RRF Score:      {result['rrf_score']:.6f}")
            print(f"Text:           {result['text']}")

        print("\n" + "=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()