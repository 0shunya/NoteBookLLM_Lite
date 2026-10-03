from app.db.database import SessionLocal
from app.services.source_builder import (
    build_source_prompt,
    build_sources,
)
from app.services.vector_search import search_similar_chunks


QUERY = "What programming languages and technologies does this person know?"


def main():
    db = SessionLocal()

    try:
        # Retrieve the most relevant chunks.
        results = search_similar_chunks(
            db=db,
            query=QUERY,
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