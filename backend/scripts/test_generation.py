from app.db.database import SessionLocal
from app.services.citation_validator import validate_citations
from app.services.generation_service import generate_answer
from app.services.source_builder import build_sources
from app.services.vector_search import search_similar_chunks


QUERY = "What programming languages and technologies does this person know?"


def main():
    db = SessionLocal()

    try:
        # 1. Retrieve the most relevant document chunks.
        results = search_similar_chunks(
            db=db,
            query=QUERY,
            limit=3,
        )

        # 2. Convert raw search results into numbered sources:
        #    [1], [2], [3], etc.
        sources = build_sources(results)

        # 3. Generate the answer using ONLY those sources.
        answer = generate_answer(
            question=QUERY,
            sources=sources,
        )

        # 4. Validate every citation ID used by the model.
        validation = validate_citations(
            answer=answer,
            sources=sources,
        )

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
        print(f"Valid: {validation['valid']}")
        print(f"Cited source IDs: {validation['cited_source_ids']}")
        print(f"Invalid source IDs: {validation['invalid_source_ids']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()