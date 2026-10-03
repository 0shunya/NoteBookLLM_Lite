from app.db.database import SessionLocal
from app.services.keyword_search import search_keyword_chunks


DOCUMENT_ID = "76fa161f-ddee-4e16-b33f-42f26682f8f4"

QUERIES = [
    "What programming languages and technologies does this person know?",
    "PostgreSQL",
    "React",
    "Python",
    "Docker",
]


def main():
    db = SessionLocal()

    try:
        for query in QUERIES:
            print("\n" + "=" * 70)
            print(f"QUERY: {query}")
            print("=" * 70)

            results = search_keyword_chunks(
                db=db,
                query=query,
                document_id=DOCUMENT_ID,
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