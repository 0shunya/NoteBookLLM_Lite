import argparse

from app.db.database import SessionLocal
from app.services.generation_service import generate_answer
from app.services.source_builder import build_sources
from app.services.vector_search import search_similar_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Try grounded generation over stored PDFs.")
    parser.add_argument("query", help="Question to ask the local model")
    parser.add_argument("--document-id", help="Restrict retrieval to one uploaded document")
    parser.add_argument("--document-ids", nargs="+", help="Restrict retrieval to these documents")
    args = parser.parse_args()
    if args.document_id and args.document_ids:
        parser.error("Use --document-id or --document-ids, not both.")
    db = SessionLocal()

    try:
        # 1. Retrieve the most relevant document chunks.
        results = search_similar_chunks(
            db=db,
            query=args.query,
            document_id=args.document_id,
            document_ids=args.document_ids,
            limit=5,
        )

        # 2. Convert raw search results into numbered sources:
        #    [1], [2], [3], etc.
        sources = build_sources(results)

        # 3. Generate the answer using ONLY those sources.
        generation = generate_answer(
            question=args.query,
            sources=sources,
        )
        answer = generation["answer"]

        print("\n===== ANSWER =====\n")
        print(answer)

        print("\n===== SOURCES USED =====\n")
        for source in sources:
            print(
                f"[{source.source_id}] "
                f"{source.filename} "
                f"p.{source.page_number}"
            )

        print("\n===== CITATION VALIDATION =====\n")
        print(f"Valid: {generation['validation']['valid']}")
        print(f"Cited source IDs: {generation['validation']['cited_source_ids']}")
        print(f"Invalid source IDs: {generation['validation']['invalid_source_ids']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
