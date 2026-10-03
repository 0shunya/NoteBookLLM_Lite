from app.db.database import SessionLocal
from app.services.hybrid_search import hybrid_search_chunks


DOCUMENT_ID = "76fa161f-ddee-4e16-b33f-42f26682f8f4"

QUERY = "What programming languages and technologies does this person know?"


def main():
    db = SessionLocal()

    try:
        results = hybrid_search_chunks(
            db=db,
            query=QUERY,
            document_id=DOCUMENT_ID,
            limit=5,
            candidate_limit=10,
        )

        print("\n===== HYBRID SEARCH RESULTS =====\n")

        for rank, result in enumerate(results, start=1):
            print(
                f"[{rank}] "
                f"chunk={result['chunk_id']} "
                f"page={result['page_number']} "
                f"RRF={result['rrf_score']:.6f} "
                f"vector_rank={result['vector_rank']} "
                f"keyword_rank={result['keyword_rank']}"
            )

            print(f"Text: {result['text']}")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    main()