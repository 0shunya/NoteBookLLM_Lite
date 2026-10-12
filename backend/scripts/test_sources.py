import argparse

from app.db.database import SessionLocal
from app.services.source_builder import (
    build_source_prompt,
    build_sources,
)
from app.services.vector_search import search_similar_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the passages used as generation sources.")
    parser.add_argument("query", help="Question to search for")
    parser.add_argument("--document-id", help="Restrict retrieval to one uploaded document")
    parser.add_argument("--document-ids", nargs="+", help="Restrict retrieval to these documents")
    args = parser.parse_args()
    if args.document_id and args.document_ids:
        parser.error("Use --document-id or --document-ids, not both.")
    db = SessionLocal()

    try:
        # Retrieve the most relevant chunks.
        results = search_similar_chunks(
            db=db,
            query=args.query,
            document_id=args.document_id,
            document_ids=args.document_ids,
            limit=3,
        )

        # Convert retrieval results into numbered sources.
        sources = build_sources(results)

        # Build the evidence block that will eventually go
        # into the LLM prompt.
        prompt = build_source_prompt(sources)

        print("\n===== SOURCES =====\n")
        print(prompt)

        print("\n===== METADATA =====\n")

        for source in sources:
            print(
                f"[{source.source_id}] "
                f"chunk={source.chunk_id} "
                f"page={source.page_number} "
                f"distance={source.distance:.4f}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()
