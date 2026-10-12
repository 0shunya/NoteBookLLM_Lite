"""Offline unit tests for the deterministic RAG and citation components."""

import sys
from pathlib import Path
import unittest
from sqlalchemy.orm import configure_mappers

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base
from app.services.citation_validator import validate_citations
from app.services.chunker import MAX_CHUNK_SIZE, create_chunks
from app.services.generation_service import SYSTEM_PROMPT, generate_answer
from app.services.hybrid_search import fuse_ranked_results, rerank_candidates
from app.services.providers.response import ModelResponse
from app.services.qa_service import build_retrieval_query
from app.services.source_builder import Source


def source() -> Source:
    return Source(
        source_id=1,
        chunk_id=101,
        document_id="doc-a",
        filename="guide.pdf",
        page_number=3,
        text="The Blue Line arrives every 12 minutes.",
        distance=0.12,
    )


class FakeGateway:
    provider_name = "fake"
    model_name = "test-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ChunkerTests(unittest.TestCase):
    def test_chunks_retain_page_and_document_metadata(self):
        text = " ".join(f"Sentence number {index} explains retrieval." for index in range(80))
        chunks = create_chunks(text, page_number=7, document_id="doc-a")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk["page_number"] == 7 for chunk in chunks))
        self.assertTrue(all(chunk["page_start"] == chunk["page_end"] == 7 for chunk in chunks))
        self.assertTrue(all(chunk["document_id"] == "doc-a" for chunk in chunks))
        self.assertTrue(all(chunk["text"] for chunk in chunks))

    def test_single_very_long_sentence_is_split(self):
        chunks = create_chunks("word " * 700, page_number=2, document_id="doc-b")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk["text"]) <= MAX_CHUNK_SIZE for chunk in chunks))

    def test_empty_page_produces_no_chunks(self):
        self.assertEqual(create_chunks("  \n  ", page_number=1, document_id="doc"), [])


class CitationTests(unittest.TestCase):
    def test_valid_citation_after_sentence_period(self):
        result = validate_citations("The Blue Line arrives every 12 minutes. [1]", [source()])
        self.assertTrue(result["valid"])
        self.assertEqual(result["cited_source_ids"], [1])

    def test_invalid_and_malformed_citations_fail(self):
        result = validate_citations("It runs hourly. [9] [not-a-source]", [source()])
        self.assertFalse(result["valid"])
        self.assertEqual(result["invalid_source_ids"], [9])
        self.assertEqual(result["malformed_citations"], ["[not-a-source]"])

    def test_uncited_factual_sentence_fails(self):
        result = validate_citations("The Blue Line arrives every 12 minutes.", [source()])
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["uncited_sentences"]), 1)

    def test_explicit_abstention_does_not_need_a_source(self):
        result = validate_citations(
            "That information was not found in the provided sources.", [source()]
        )
        self.assertTrue(result["valid"])

    def test_clear_source_absence_statement_does_not_need_a_citation(self):
        result = validate_citations(
            "The provided sources do not state the borrowing limit.", [source()]
        )
        self.assertTrue(result["valid"])

    def test_citation_before_period_is_accepted(self):
        result = validate_citations("The fare is $2.75 [1].", [source()])
        self.assertTrue(result["valid"])

    def test_time_abbreviations_do_not_split_a_cited_sentence(self):
        result = validate_citations(
            "The library is open from 8:00 a.m. to 8:00 p.m. [1]", [source()]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["uncited_sentences"], [])

    def test_sentence_boundary_after_citation_is_detected(self):
        result = validate_citations(
            "Open at 8:00 a.m. [1] The clinic closes at 6:00 p.m. [1]",
            [source()],
        )
        self.assertTrue(result["valid"])


class RetrievalTests(unittest.TestCase):
    def test_rrf_merges_candidates_and_preserves_rank_metadata(self):
        vector = [
            {"chunk_id": 1, "document_id": "a", "page_number": 1, "text": "alpha"},
            {"chunk_id": 2, "document_id": "b", "page_number": 2, "text": "beta"},
        ]
        keyword = [
            {"chunk_id": 2, "document_id": "b", "page_number": 2, "text": "beta", "rank": 1.0},
            {"chunk_id": 3, "document_id": "c", "page_number": 3, "text": "gamma", "rank": 0.5},
        ]
        fused = fuse_ranked_results(vector, keyword)
        self.assertEqual(fused[0]["chunk_id"], 2)
        by_id = {item["chunk_id"]: item for item in fused}
        self.assertEqual(by_id[2]["vector_rank"], 2)
        self.assertEqual(by_id[2]["keyword_rank"], 1)
        self.assertEqual(by_id[3]["vector_rank"], None)

    def test_lexical_reranker_can_promote_full_query_match(self):
        candidates = [
            {"chunk_id": 1, "text": "A general page about schedules.", "rrf_score": 0.032},
            {"chunk_id": 2, "text": "The Blue Line arrives every 12 minutes.", "rrf_score": 0.025},
        ]
        ranked = rerank_candidates("Blue Line every 12 minutes", candidates)
        self.assertEqual(ranked[0]["chunk_id"], 2)
        self.assertGreater(ranked[0]["query_term_coverage"], ranked[1]["query_term_coverage"])

    def test_follow_up_query_uses_prior_user_question_for_retrieval(self):
        expanded = build_retrieval_query(
            "Which one has the shortest wait?",
            [{"role": "user", "content": "How often does the Blue Line arrive?"}],
        )
        self.assertIn("Blue Line", expanded)
        self.assertIn("shortest wait", expanded)


class GenerationTests(unittest.TestCase):
    def test_prompt_requires_direct_evidence_for_the_requested_attribute(self):
        self.assertIn("specific fact requested", SYSTEM_PROMPT)
        self.assertIn("related number", SYSTEM_PROMPT)
        self.assertIn("one concise sentence", SYSTEM_PROMPT)

    def test_invalid_first_attempt_is_retried_and_each_attempt_is_returned(self):
        gateway = FakeGateway([
            ModelResponse("The train is fast.", "fake", "test-model", 12, 4, 21),
            ModelResponse("The Blue Line arrives every 12 minutes. [1]", "fake", "test-model", 18, 8, 24),
        ])
        result = generate_answer("How often does the Blue Line arrive?", [source()], model_gateway=gateway)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["answer"], "The Blue Line arrives every 12 minutes. [1]")
        self.assertEqual([item.status for item in result["attempts"]], ["retry", "success"])
        self.assertEqual([item.attempt_number for item in result["attempts"]], [1, 2])
        self.assertEqual(len(gateway.calls), 2)
        self.assertIn("validation errors", gateway.calls[1]["user_prompt"].lower())

    def test_retry_limit_returns_safe_failure(self):
        gateway = FakeGateway([
            ModelResponse("Unsupported answer.", "fake", "test-model"),
            ModelResponse("Still unsupported.", "fake", "test-model"),
            ModelResponse("Must never be called.", "fake", "test-model"),
        ])
        result = generate_answer("Question", [source()], model_gateway=gateway, max_attempts=2)
        self.assertEqual(result["status"], "failure")
        self.assertEqual(len(gateway.calls), 2)
        self.assertEqual([item.status for item in result["attempts"]], ["retry", "failure"])
        self.assertIn("citation validation", result["answer"])

    def test_provider_error_is_a_recordable_bounded_attempt(self):
        gateway = FakeGateway([
            TimeoutError("local model timed out"),
            ModelResponse("The Blue Line arrives every 12 minutes. [1]", "fake", "test-model"),
        ])
        result = generate_answer("Question", [source()], model_gateway=gateway)
        self.assertEqual([attempt.status for attempt in result["attempts"]], ["retry", "success"])
        self.assertIn("timed out", result["attempts"][0].error)

    def test_all_provider_errors_return_canonical_validation_shape(self):
        gateway = FakeGateway([TimeoutError("timeout"), TimeoutError("timeout")])
        result = generate_answer("Question", [source()], model_gateway=gateway)
        self.assertEqual(result["status"], "failure")
        self.assertFalse(result["validation"]["valid"])
        self.assertEqual(result["validation"]["cited_source_ids"], [])
        self.assertEqual(len(result["validation"]["model_errors"]), 2)

    def test_no_sources_does_not_call_a_model(self):
        gateway = FakeGateway([])
        result = generate_answer("Question", [], model_gateway=gateway)
        self.assertEqual(result["attempts"], [])
        self.assertEqual(gateway.calls, [])
        self.assertIn("not found", result["answer"].lower())


class SchemaTests(unittest.TestCase):
    def test_core_tables_cover_notebooks_citations_and_model_attempts(self):
        expected = {
            "notebooks", "documents", "chunks", "embeddings", "conversations",
            "messages", "citations", "model_calls",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables))

    def test_orm_relationships_configure(self):
        configure_mappers()


if __name__ == "__main__":
    unittest.main(verbosity=2)
