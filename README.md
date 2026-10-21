# NotebookLLM Lite

NotebookLLM Lite is a local-first document question-answering app. Add PDFs to a notebook, open a PDF for its own conversation history, and inspect the document and page behind each cited answer.

## Cloud edition

The `cloud/` directory contains the Convex, Better Auth, Supabase Storage, and Gemini cloud edition. The root app remains the local version. The cloud edition uses separate cloud data and does not copy the local PostgreSQL database or PDFs automatically. See [cloud/README.md](cloud/README.md) for local cloud setup and deployment steps.

## Problem

General chat models can answer confidently without showing where a claim came from. NotebookLLM Lite retrieves passages from the user's documents, limits generation to those passages, checks citation markers, and keeps a trace of every embedding and generation call.

## Features

- Notebook-based PDF libraries with upload status, duplicate detection, retained originals, and confirmed deletion.
- Page-aware text extraction and sentence/paragraph chunking with overlap.
- Local `nomic-embed-text` embeddings stored in PostgreSQL with pgvector.
- PostgreSQL full-text search combined with vector retrieval using Reciprocal Rank Fusion (RRF).
- A deterministic lexical reranking step that promotes passages matching more query terms.
- Direct document, notebook, and multi-document one-shot QA, with conversations scoped to one selected document.
- Per-document chat history with conversation titles derived from the first question.
- Selectable local Ollama, Gemini API, or optional OpenAI answer generation; embeddings and retrieval remain local.
- Bounded answer retries when citations are missing, malformed, or refer to sources that were not sent to the model.
- Persistent citation records that link answer markers to document pages and excerpts.
- Per-attempt model-call traces, including generation and embedding calls.
- A responsive browser interface served by FastAPI; there is no separate frontend build step.
- A committed golden set and local evaluation runner.

## Architecture

```text
Browser UI
    |
    v
FastAPI routes and Pydantic schemas
    |
    +--> PDF upload --> local file storage --> background ingestion
    |                                      |
    |                         pypdf -> page-aware chunks
    |                                      |
    |                         Ollama embeddings
    |                                      |
    +-------------------------------- PostgreSQL + pgvector
                                           |
Question + notebook / conversation       |
    |                                      |
    +--> query embedding --> vector search |
    +--> PostgreSQL full-text search ------+
                 |
             RRF fusion
                 |
       lexical coverage reranking
                 |
       numbered source excerpts
                 |
         model gateway -> Ollama
                 |
       citation validation + retry
                 |
       answer, citations, model_calls
```

## RAG pipeline

`PDF upload → hash and store original → extract each page → chunk within page boundaries → embed in batches → persist chunks and vectors → run vector and keyword search → fuse ranks with RRF → rerank by query-term coverage → generate from numbered excerpts → validate citations → store answer, citation rows, and call trace`.

Chunks target 1,400 characters with about 140 characters of overlap. Pages are parsed before chunking, so a citation retains its source page. The current parser handles text-based PDFs; it reports pages with little or no extractable text because OCR is not enabled.

The reranker is intentionally small and inspectable. It scores each result as `0.8 × normalized RRF + 0.2 × query-term coverage`. It adds no separate model or API dependency. Whether it helps is measured in the evaluation section below.

## Tech stack

- **API:** Python, FastAPI, Pydantic
- **Database:** PostgreSQL 17, SQLAlchemy 2, pgvector
- **PDF parsing:** pypdf
- **Models:** Ollama
- **Frontend:** HTML, CSS, and browser JavaScript, served by FastAPI
- **Schema changes:** Alembic migrations, including an upgrade path that groups legacy documents in an `Imported documents` notebook

## Models

| Purpose | Default | Provider |
| --- | --- | --- |
| Answer generation | `gemma2:2b` | Ollama, local |
| Text embeddings | `nomic-embed-text` (768 dimensions) | Ollama, local |
| Optional answer generation | `gemini-3.8-flash` | Gemini API, requires `GEMINI_API_KEY` |

Models are selected through environment settings. Ollama remains the default and needs no API key. Gemini uses the `GEMINI_API_KEY` and `GEMINI_MODEL` settings. An optional OpenAI chat adapter is available through `backend/requirements-openai.txt` and `MODEL_PROVIDER=openai`.

## Evaluation

The committed benchmark has 40 questions over a small, synthetic 10-page corpus: 30 answerable questions and 10 questions whose answers are absent. The retrieval run below used the configured local Nomic embedding model. The keyword ranking in this in-memory benchmark uses deterministic token overlap; it does not exercise PostgreSQL full-text search or pgvector's HNSW index. Production generation defaults to the top three reranked passages because the measured reranker reached Hit@3 1.0000 on this fixture.

| Retrieval mode | Hit@1 | Hit@3 | Hit@5 | MRR@5 |
| --- | ---: | ---: | ---: | ---: |
| Vector only | 0.9000 | 1.0000 | 1.0000 | 0.9500 |
| Vector + keyword with RRF | 0.9333 | 1.0000 | 1.0000 | 0.9667 |
| RRF + lexical reranking | 0.9667 | 1.0000 | 1.0000 | 0.9833 |

The full local `gemma2:2b` run with three retrieved passages measured:

| Generation metric | Result |
| --- | ---: |
| Citation precision (gold-page match) | 0.7436 |
| Citation recall (gold-page match) | 0.9667 |
| Answer-term recall | 0.9348 |
| Correct refusal rate on absent-answer cases | 0.5000 |
| Citation syntax/source validation pass rate | 1.0000 |
| Mean generation attempts per question | 1.000 |
| Generation latency p50 / p95 | 13,444 / 16,248 ms |

These scores are on a small synthetic fixture, not arbitrary user PDFs. The 100% validation rate checks citation structure and source IDs only; it does not detect unsupported claims. The model correctly refused only 5 of 10 absent-answer questions, so improving refusal behavior is the largest measured quality gap. Citation precision and recall compare source pages with gold labels and are not entailment scores. Run the local evaluation to reproduce them:

```powershell
cd backend
python scripts/run_evaluation.py
```

The JSON report is written under the ignored `backend/evaluation-results/` directory. A retrieval-only run skips chat generation:

```powershell
python scripts/run_evaluation.py --skip-generation
```

Run the offline service tests with:

```powershell
python -m unittest discover -s tests -v
```

The evaluation runner uses real local Ollama embeddings and generation. It is independent of PostgreSQL so it can produce a repeatable fixture score without a database. Its keyword branch approximates the production full-text candidate ranking, and its citation metrics compare model-cited pages with the gold page labels; they are not an entailment judge.

## Observability

`model_calls` stores one row per actual query embedding, document-embedding batch, and generation attempt. Rows include a trace ID, feature, provider, model, prompt version, attempt number, token counts when the provider exposes them, cost, latency, status, validation details, and provider errors. `/traces/{trace_id}` returns the attempts for a QA trace; `/model-calls` lists recent calls.

Local Ollama calls are recorded at `$0` provider cost. This does not include electricity or hardware cost. Cost for an optional hosted provider is left unknown until provider pricing is explicitly configured.

## Local setup

Prerequisites: Python 3.11 or newer, Docker Desktop, and [Ollama](https://ollama.com/download).

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d
ollama pull gemma2:2b
ollama pull nomic-embed-text
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000). The API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs). PostgreSQL credentials and model names can be changed in `.env`.

To try Gemini, create a key in [Google AI Studio](https://aistudio.google.com/app/apikey), then edit the repository-root `.env` file and set:

```dotenv
MODEL_PROVIDER=gemini
GEMINI_MODEL=gemini-3.8-flash
GEMINI_API_KEY=your-key-here
```

Restart the API after changing `.env`. Keep the key there; `.env` is ignored by Git. When Gemini is selected, the question, recent chat context, and retrieved document excerpts are sent to Google's API for answer generation. PDF storage, embeddings, and retrieval remain local. Ollama still needs to be running for embeddings.

Select a PDF in the Documents list to open its chats. Use the history menu to return to an earlier conversation, or the plus button to start a new one. The delete button beside a document asks for confirmation and removes that PDF and its chat history.

The API uses FastAPI's in-process background task mechanism for PDF parsing and indexing. Keep the API process running while a new PDF is being indexed. A durable multi-process job queue is a production follow-up.

## API

| Route | Purpose |
| --- | --- |
| `POST /notebooks` / `GET /notebooks` | Create and list notebooks |
| `POST /notebooks/{id}/documents` | Upload a PDF and return its queued document record |
| `GET /notebooks/{id}/documents` | List notebook documents and indexing states |
| `GET /documents/{id}` / `DELETE /documents/{id}` | Inspect or remove a source |
| `GET /documents/{id}/conversations` | List chats scoped to one document |
| `GET /documents/{id}/pages/{page}` | Read extracted text for a cited page |
| `POST /notebooks/{id}/ask` | Ask across all PDFs in a notebook |
| `POST /ask` | Ask across a document, document list, or notebook |
| `POST /conversations` | Create a conversation for one document (`document_id` required) |
| `POST /conversations/{id}/messages` | Ask a conversational follow-up about that document |
| `GET /conversations/{id}` | Read messages and stored citations |
| `GET /traces/{trace_id}` | Inspect every model call in one QA trace |

The original `POST /upload` route remains available for direct, non-notebook uploads.

## Limitations

- OCR, image-only PDF parsing, Markdown uploads, streaming responses, authentication, and authorization are not implemented.
- PDF indexing runs in the API process. A process restart during ingestion can leave a document queued or processing; a persistent worker queue is needed for production deployment.
- Citation validation checks citation syntax, sentence coverage, and source IDs. It does not prove that the cited passage entails the sentence; the evaluation's page-level citation score is only a source-match proxy.
- In the committed 40-question synthetic evaluation, the default `gemma2:2b` model correctly refused only 5 of 10 questions whose answers were absent. Treat this as a measured limitation, not a faithfulness guarantee.
- The lexical reranker is not a neural cross-encoder. The committed benchmark is small and synthetic.
- The local Compose file starts PostgreSQL only. Ollama and the API run as host processes.

## Future improvements

Add a durable Postgres-backed ingestion queue and worker, OCR for scanned documents, page-level citation highlighting in the PDF viewer, streamed answers, authentication, broader user-document evaluation, and an entailment-based faithfulness grader. Compare the lexical reranker with a local cross-encoder only if a larger evaluation set shows it is worthwhile.
