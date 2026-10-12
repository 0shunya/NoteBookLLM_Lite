# NotebookLM Lite: interview notes

These notes describe the current implementation. The evaluation results refer to the committed synthetic corpus and should not be generalized to arbitrary documents.

## Why RAG?

The application answers questions about a user's own PDFs. A model by itself does not have reliable access to those documents, and a parametric answer can sound plausible without evidence. Retrieval selects relevant document passages for each question; generation uses those passages as its evidence and returns page citations.

## Why PostgreSQL and pgvector?

The project already uses PostgreSQL for documents, chunks, conversations, messages, model calls, and citations. pgvector keeps dense vectors beside those records, so retrieval can join scores to a filename, page, and conversation scope in SQL. It avoids a separate vector service for this local-scale app.

The Alembic upgrade migration assigns documents from the original notebook-less schema to an `Imported documents` notebook so they remain visible through the new notebook UI.

## Why hybrid search?

Vector search is useful for paraphrases, while keyword search is useful for names, dates, codes, and exact phrases. Both candidate lists are filtered to the documents attached to a notebook or conversation, then merged by Reciprocal Rank Fusion.

## What is RRF?

For each result list, RRF adds `1 / (k + rank)` to a chunk's score. This implementation uses `k = 60`. A chunk that ranks well in both retrieval methods receives support from both lists. RRF avoids adding raw cosine distances to PostgreSQL text ranks, which use different scales.

## Why rerank after RRF?

RRF is the fusion step. The current reranker adds a second relevance check: normalized RRF contributes 80% of the score, and the fraction of non-stopword query terms present in the passage contributes 20%. This is deterministic and needs no extra model. The local golden-set run increased Hit@1 from 0.9000 for vector-only retrieval to 0.9667 after RRF and lexical reranking; Hit@5 stayed at 1.0000. This is a result on ten synthetic pages, not a broad benchmark.

## How are chunks created?

`pypdf` extracts each PDF page separately. Paragraphs and sentences are packed into chunks of up to about 1,400 characters, with about 140 characters of overlap. A very long sentence is split on a word boundary as a last resort. Chunks are never intentionally merged across pages.

## Why keep page metadata?

The answer refers to a real file and page, so each chunk stores `page_number`, `page_start`, and `page_end`. The current chunker keeps all three values on one page. That makes page references accurate and leaves the schema able to represent a future chunk spanning pages.

## How are citations generated?

The retrieval results are numbered for a single generation request. The prompt includes each marker with its filename, page, and excerpt. The model must put one or more markers after every factual sentence. Source numbers are request-scoped and map back to chunk IDs and document records.

## How are citations validated and stored?

The validator checks that each factual sentence has a marker, every marker is well formed, and every marker refers to a source actually sent to the model. A bounded retry sends the prior draft and validation errors back to the model. After the retry limit, the service returns a safe failure answer. Successful answer markers are stored in `citations` with the chunk, quote, and page. This is structural validation; it does not prove entailment.

The sentence splitter accounts for common abbreviations such as `a.m.` and `p.m.` and for a new sentence after a citation marker. Without that handling, a period inside a time could be mistaken for the end of an uncited sentence.

## How do retries work?

The default maximum is two generation attempts. Each actual generation call produces an attempt result with provider, model, latency, token counts where available, status, validation output, and any error. The API persists each attempt as a separate `model_calls` row. Query embeddings use the same trace ID with a separate feature label, so the retrieval and generation calls can be inspected together.

## How is hallucination reduced?

The prompt says to use only retrieved sources, treats conversation history as context rather than evidence, and tells the model to abstain when the excerpts do not answer the question. Code rejects malformed or unknown citations, retries a failed answer once, and hides a response that still fails citation validation. These checks reduce risk; they do not establish semantic faithfulness.

## How does model-call observability work?

`model_calls` captures query embeddings, document embedding batches, and each generation attempt. It records trace ID, feature, provider, model, prompt version, attempt, token counts, provider cost, latency, status, citation-validation details, and provider error. Local provider cost is stored as zero; hosted provider cost is unknown unless pricing is configured.

## How is evaluation performed?

`backend/evaluation/golden_set.jsonl` contains 30 answerable and 10 unanswerable questions over five synthetic documents. `backend/scripts/run_evaluation.py` computes Hit@1/3/5 and MRR@5 for vector-only, RRF, and reranked results. The full run also calls the configured local model and records answer-term recall, citation precision and recall against gold pages, correct refusals, citation-validation pass rate, attempts, and generation p50/p95 latency. Keyword candidate ranking in this in-memory runner uses token overlap; it does not exercise PostgreSQL full-text indexing, pgvector HNSW, or database logging. The citation metrics are page-label checks, not an entailment judge.

On the measured 40-question run with `gemma2:2b` and three passages, answer-term recall was 0.9348, citation precision 0.7436, citation recall 0.9667, and citation validation passed on all answers. The model correctly refused only 5 of the 10 absent-answer questions. The syntax pass rate therefore must not be read as a semantic faithfulness score.

## What happens when the answer is absent?

When retrieval produces no candidates, the service returns an explicit no-information response without calling the generator. If it finds passages that do not answer the question, the model is instructed to abstain. The golden set includes ten absent-answer cases so that refusal behavior can be measured.

## How does multi-document retrieval work?

A conversation can be attached to several documents. A conversation created for a notebook scopes retrieval to all documents in that notebook. Both vector and keyword queries receive the same document ID filter; returned chunks retain their own document and page fields, so citations can cross files without losing source identity.

## Why Ollama?

Ollama keeps both generation and embeddings local and does not require paid API access. The defaults are `gemma2:2b` for answer generation and `nomic-embed-text` for embeddings. Provider calls are isolated behind an adapter and gateway; OpenAI support is optional.

## What are the current limitations?

The parser does not OCR scanned PDFs. Ingestion uses FastAPI's in-process background tasks rather than a durable worker queue. The app has no authentication, streaming, or authorization. Citation checks verify form and source identity, not semantic support. The evaluation fixture is deliberately small and synthetic, and the reranker is lexical.

The default small local model can still answer with a related but unsupported fact when the requested detail is absent. The measured refusal rate is 50% on the current synthetic set; broader evaluation and stronger evidence verification are needed before treating its answers as reliable.

## What would change for production scale?

I would first add a persistent ingestion queue with idempotent jobs and a separate worker, then define tenancy and authorization around notebooks and object storage. I would evaluate query filters and HNSW recall with realistic multi-tenant data, add robust file limits and malware checks, include OCR, and use broader human-reviewed evaluation data. I would only adopt a cross-encoder or external observability platform after the evaluation shows a measurable need.
