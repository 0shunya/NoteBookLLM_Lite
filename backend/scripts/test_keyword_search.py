import argparse

from app.db.database import SessionLocal
from app.services.keyword_search import search_keyword_chunks


QUERIES = [
    "What programming languages and technologies does this person know?",
    "PostgreSQL",
    "React",
    "Python",
    "Docker",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect PostgreSQL full-text search results.")
    parser.add_argument("--document-id", help="Restrict retrieval to one uploaded document")
    parser.add_argument("--document-ids", nargs="+", help="Restrict retrieval to these documents")
    parser.add_argument("queries", nargs="*", help="Queries (defaults to a small sample set)")
    args = parser.parse_args()
    if args.document_id and args.document_ids:
        parser.error("Use --document-id or --document-ids, not both.")
    queries = args.queries or QUERIES
    db = SessionLocal()

    try:
        for query in queries:
            print("\n" + "=" * 70)
            print(f"QUERY: {query}")
            print("=" * 70)

            results = search_keyword_chunks(
                db=db,
                query=query,
                document_id=args.document_id,
                document_ids=args.document_ids,
                limit=5,
            )

            if not results:
                print("No results found.")
                continue

            for index, result in enumerate(results, start=1):
                print(
                    f"\nRank: {index}"
                    f"\nChunk: {result['chunk_id']}"
                    f"\nPage: {result['page_number']}"
                    f"\nScore: {result['rank']:.4f}"
                    f"\nText: {result['text']}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    main()
