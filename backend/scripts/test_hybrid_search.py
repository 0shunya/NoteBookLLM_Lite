import argparse

from app.db.database import SessionLocal
from app.services.hybrid_search import hybrid_search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect hybrid retrieval results.")
    parser.add_argument("query", help="Question to search for")
    parser.add_argument("--document-id", help="Restrict retrieval to one uploaded document")
    parser.add_argument("--document-ids", nargs="+", help="Restrict retrieval to these documents")
    args = parser.parse_args()
    if args.document_id and args.document_ids:
        parser.error("Use --document-id or --document-ids, not both.")
    db = SessionLocal()

    try:
        results = hybrid_search_chunks(
            db=db,
            query=args.query,
            document_id=args.document_id,
            document_ids=args.document_ids,
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
