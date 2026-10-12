import argparse

from app.db.database import SessionLocal
from app.services.hybrid_search import hybrid_search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Search several uploaded documents together.")
    parser.add_argument("query", help="Question to search for")
    parser.add_argument("document_ids", nargs="+", help="IDs returned by the upload API")
    args = parser.parse_args()
    db = SessionLocal()

    try:
        results = hybrid_search_chunks(
            db=db,
            query=args.query,
            document_ids=args.document_ids,
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
