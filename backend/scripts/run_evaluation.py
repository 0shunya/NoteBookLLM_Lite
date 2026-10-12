"""Run the committed RAG golden set with the configured local models.

The benchmark keeps a small, known corpus in memory so retrieval and local
generation can be measured without PostgreSQL. It uses the real configured
Ollama embedding and generation models; keyword candidate ranking is a
transparent token-overlap approximation, so these results do not replace an
integration evaluation against PostgreSQL/pgvector.
"""

import argparse
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.citation_validator import _is_explicit_refusal
from app.services.embedding_service import generate_embeddings
from app.services.generation_service import generate_answer
from app.services.hybrid_search import fuse_ranked_results, rerank_candidates
from app.services.keyword_search import STOPWORDS
from app.services.source_builder import build_sources


CORPUS_PATH = BACKEND_DIR / "evaluation" / "corpus.jsonl"
GOLDEN_SET_PATH = BACKEND_DIR / "evaluation" / "golden_set.jsonl"
OUTPUT_PATH = BACKEND_DIR / "evaluation-results" / "latest.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    }


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def build_keyword_ranking(question: str, corpus: list[dict]) -> list[dict]:
    query_terms = terms(question)
    ranked = []
    for item in corpus:
        document_terms = terms(item["text"])
        overlap = len(query_terms & document_terms)
        if overlap:
            ranked.append({
                **item,
                "rank": overlap / math.sqrt(max(1, len(query_terms) * len(document_terms))),
            })
    return sorted(ranked, key=lambda item: (-item["rank"], item["document_id"], item["page_number"]))


def is_gold(result: dict, row: dict) -> bool:
    return any(
        result["document_id"] == gold["document_id"]
        and result["page_number"] == gold["page_number"]
        for gold in row["gold_sources"]
    )


def ranking_metrics(rows: list[dict], rankings: dict[str, dict[str, list[dict]]]) -> dict:
    answerable = [row for row in rows if row["answerable"]]
    result = {}
    for name, by_query in rankings.items():
        if not answerable:
            result[name] = {
                "hit_at_1": None,
                "hit_at_3": None,
                "hit_at_5": None,
                "mrr_at_5": None,
            }
            continue
        hits = {k: [] for k in (1, 3, 5)}
        reciprocal_ranks = []
        for row in answerable:
            found = next(
                (rank for rank, item in enumerate(by_query[row["id"]], start=1) if is_gold(item, row)),
                None,
            )
            for k in hits:
                hits[k].append(bool(found and found <= k))
            reciprocal_ranks.append(1 / found if found and found <= 5 else 0.0)
        result[name] = {
            **{f"hit_at_{k}": round(sum(values) / len(values), 4) for k, values in hits.items()},
            "mrr_at_5": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4),
        }
    return result


def evaluate_generation(rows: list[dict], ranked_results: dict[str, list[dict]]) -> tuple[dict, list[dict]]:
    answerable = [row for row in rows if row["answerable"]]
    unanswerable = [row for row in rows if not row["answerable"]]
    correct_refusals = 0
    citation_true_positives = 0
    citation_count = 0
    gold_page_recall = 0
    gold_page_count = 0
    answer_term_hits = 0
    answer_term_count = 0
    validation_passes = 0
    attempts_per_query = []
    latencies = []
    details = []

    for row in rows:
        candidates = ranked_results[row["id"]][: settings.retrieval_result_limit]
        sources = build_sources(candidates)
        started = time.perf_counter()
        generation = generate_answer(row["question"], sources)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        attempts_per_query.append(len(generation["attempts"]))
        latencies.append(elapsed_ms)
        validation = generation["validation"]
        validation_passes += int(bool(validation.get("valid")))
        source_by_id = {source.source_id: source for source in sources}
        cited_ids = validation.get("cited_source_ids", [])
        cited_sources = [source_by_id[item] for item in cited_ids if item in source_by_id]
        gold_keys = {
            (gold["document_id"], gold["page_number"])
            for gold in row["gold_sources"]
        }
        cited_keys = {(source.document_id, source.page_number) for source in cited_sources}
        citation_count += len(cited_ids)
        citation_true_positives += sum(key in gold_keys for key in cited_keys)
        if row["answerable"]:
            gold_page_count += len(gold_keys)
            gold_page_recall += len(gold_keys & cited_keys)
            expected = row["expected_terms"]
            answer_term_count += len(expected)
            answer_term_hits += sum(term.lower() in generation["answer"].lower() for term in expected)
        else:
            correct_refusals += int(_is_explicit_refusal(generation["answer"]))

        details.append({
            "id": row["id"],
            "answerable": row["answerable"],
            "answer": generation["answer"],
            "status": generation["status"],
            "citation_validation": validation,
            "cited_sources": [
                {"document_id": source.document_id, "page_number": source.page_number}
                for source in cited_sources
            ],
            "retrieved_sources": [
                {"document_id": source.document_id, "page_number": source.page_number}
                for source in sources
            ],
            "latency_ms": elapsed_ms,
            "attempts": [
                {
                    "attempt_number": attempt.attempt_number,
                    "status": attempt.status,
                    "latency_ms": attempt.latency_ms,
                    "input_tokens": attempt.input_tokens,
                    "output_tokens": attempt.output_tokens,
                    "validation": attempt.validation,
                    "error": attempt.error,
                }
                for attempt in generation["attempts"]
            ],
        })

    precision = citation_true_positives / citation_count if citation_count else 0.0
    recall = gold_page_recall / gold_page_count if gold_page_count else 0.0
    return {
        "citation_precision": round(precision, 4),
        "citation_recall": round(recall, 4),
        "answer_term_recall": round(answer_term_hits / answer_term_count, 4) if answer_term_count else 0.0,
        "correct_refusal_rate": round(correct_refusals / len(unanswerable), 4) if unanswerable else 0.0,
        "citation_validation_pass_rate": round(validation_passes / len(rows), 4),
        "mean_attempts_per_question": round(statistics.mean(attempts_per_query), 3),
        "latency_ms_p50": round(statistics.median(latencies)) if latencies else 0,
        "latency_ms_p95": round(sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1]) if latencies else 0,
    }, details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-generation", action="store_true", help="Report retrieval metrics without calling the chat model.")
    parser.add_argument("--limit", type=int, help="Run only the first N golden questions (useful for a smoke check).")
    parser.add_argument("--unanswerable-only", action="store_true", help="Evaluate only questions whose answers are absent from the sources.")
    args = parser.parse_args()

    corpus = read_jsonl(CORPUS_PATH)
    for chunk_id, item in enumerate(corpus, start=1):
        item["chunk_id"] = chunk_id
    rows = read_jsonl(GOLDEN_SET_PATH)
    if args.unanswerable_only:
        rows = [row for row in rows if not row["answerable"]]
    if args.limit:
        rows = rows[: max(1, args.limit)]
    if not corpus or not rows:
        raise SystemExit("Evaluation corpus or golden set is empty.")

    corpus_vectors = generate_embeddings([item["text"] for item in corpus])
    query_vectors = generate_embeddings([row["question"] for row in rows])
    rankings: dict[str, dict[str, list[dict]]] = {
        "vector": {},
        "hybrid_rrf": {},
        "hybrid_reranked": {},
    }
    reranked_by_query: dict[str, list[dict]] = {}

    for row, query_vector in zip(rows, query_vectors, strict=True):
        vector_results = []
        for item, vector in zip(corpus, corpus_vectors, strict=True):
            similarity = cosine_similarity(query_vector, vector)
            vector_results.append({**item, "distance": 1.0 - similarity, "model": settings.embedding_model})
        vector_results.sort(key=lambda item: (item["distance"], item["document_id"], item["page_number"]))
        keyword_results = build_keyword_ranking(row["question"], corpus)
        fused = fuse_ranked_results(vector_results, keyword_results)
        reranked = rerank_candidates(row["question"], fused)
        rankings["vector"][row["id"]] = vector_results
        rankings["hybrid_rrf"][row["id"]] = fused
        rankings["hybrid_reranked"][row["id"]] = reranked
        reranked_by_query[row["id"]] = reranked

    report = {
        "dataset": str(GOLDEN_SET_PATH.relative_to(ROOT_DIR)).replace("\\", "/"),
        "dataset_size": len(rows),
        "answerable_questions": sum(row["answerable"] for row in rows),
        "unanswerable_questions": sum(not row["answerable"] for row in rows),
        "generation_model": settings.generation_model,
        "embedding_model": settings.embedding_model,
        "retrieval_metrics": ranking_metrics(rows, rankings),
        "evaluation_notes": [
            "Local Ollama embeddings are measured on the committed synthetic corpus.",
            "Keyword ranks use deterministic token overlap; PostgreSQL full-text and pgvector integration are not exercised by this in-memory runner.",
            "Retrieval metrics are null when the selected evaluation subset has no answerable questions.",
        ],
    }

    if not args.skip_generation:
        generation_metrics, details = evaluate_generation(rows, reranked_by_query)
        report["generation_metrics"] = generation_metrics
        report["questions"] = details

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "questions"}, indent=2))
    print(f"Detailed report: {OUTPUT_PATH.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
