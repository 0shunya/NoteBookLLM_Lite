"""FastAPI application for NotebookLM Lite."""

import hashlib
import logging
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal, engine, get_db
from app.db.models import Citation, Chunk, Conversation, Document, Message, ModelCall, Notebook
from app.schemas import (
    AnswerResponse,
    AskRequest,
    ConversationCreateRequest,
    ConversationMessageRequest,
    ConversationResponse,
    DocumentResponse,
    HealthResponse,
    MessageResponse,
    ModelCallResponse,
    NotebookCreateRequest,
    NotebookResponse,
    NotebookAskRequest,
    PageResponse,
)
from app.services.embedding_indexer import embed_document_chunks
from app.services.model_call_service import create_trace_id
from app.services.pdf_parser import extract_document
from app.services.qa_service import answer_from_documents, source_response


logger = logging.getLogger("notebooklm")
ROOT_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = ROOT_DIR / "backend" / "uploads"
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(
    title="NotebookLM Lite",
    description=(
        "Local, citation-grounded document QA using FastAPI, PostgreSQL/pgvector, "
        "and Ollama."
    ),
    version="2.0.0",
)


def _document_response(document: Document) -> dict:
    return {
        "id": document.id,
        "document_id": document.id,
        "notebook_id": document.notebook_id,
        "filename": document.filename,
        "page_count": document.page_count,
        "status": document.status,
        "ingestion_error": document.ingestion_error,
        "ingestion_warnings": document.ingestion_warnings or [],
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _source_map(sources: list, cited_ids: list[int]) -> dict[int, object]:
    return {source.source_id: source for source in sources if source.source_id in cited_ids}


def _persist_citations(db: Session, message: Message, result: dict) -> None:
    validation = result["validation"]
    if not validation.get("valid"):
        return
    sources = _source_map(result.get("sources", []), validation.get("cited_source_ids", []))
    for source in sources.values():
        db.add(
            Citation(
                message_id=message.id,
                chunk_id=source.chunk_id,
                marker=source.source_id,
                quote=source.text[:1200],
                page_number=source.page_number,
            )
        )


def _answer_response(question: str, result: dict) -> dict:
    return {
        "question": question,
        "answer": result["answer"],
        "trace_id": result.get("trace_id"),
        "sources": [source_response(source) for source in result.get("sources", [])],
        "citation_validation": result["validation"],
        "generation_attempts": len(result.get("attempts", [])),
        "status": result.get("status", "success"),
    }


def _ingest_document(document_id: str) -> None:
    """Parse, chunk, and embed one queued PDF in a FastAPI worker thread."""
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        if document.status == "indexed":
            return
        document.status = "processing"
        document.ingestion_error = None
        db.commit()

        if not document.storage_key:
            raise ValueError("The original uploaded file is missing from storage.")
        file_path = UPLOAD_DIR / Path(document.storage_key).name
        if not file_path.is_file():
            raise ValueError("The original uploaded file could not be found.")

        extracted = extract_document(str(file_path), document.id)
        document.page_count = extracted.page_count
        document.ingestion_warnings = extracted.warnings
        db.commit()
        if not extracted.chunks:
            raise ValueError(
                "No readable PDF text was found. Scanned PDFs need OCR, which is not enabled."
            )

        db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        db.flush()
        db.add_all(
            Chunk(
                document_id=document.id,
                chunk_index=index,
                page_number=chunk["page_number"],
                page_start=chunk["page_start"],
                page_end=chunk["page_end"],
                text=chunk["text"],
            )
            for index, chunk in enumerate(extracted.chunks, start=1)
        )
        db.flush()
        embed_document_chunks(db, document.id)

        document = db.get(Document, document_id)
        if document is not None:
            document.status = "indexed"
            document.ingestion_error = None
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("PDF ingestion failed for document %s", document_id)
        document = db.get(Document, document_id)
        if document is not None:
            document.status = "failed"
            document.ingestion_error = f"{type(exc).__name__}: {exc}"[:500]
            db.commit()
    finally:
        db.close()


async def _save_upload(
    *,
    file: UploadFile,
    notebook_id: str | None,
    db: Session,
    background_tasks: BackgroundTasks,
) -> dict:
    filename = Path(file.filename or "document.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")
    if len(filename) > 255:
        filename = filename[-255:]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    document_id = str(uuid.uuid4())
    storage_key = f"{document_id}.pdf"
    file_path = UPLOAD_DIR / storage_key
    digest = hashlib.sha256()
    byte_count = 0
    header = b""

    try:
        with file_path.open("xb") as output:
            while block := await file.read(1024 * 1024):
                if not header:
                    header = block[:1024]
                byte_count += len(block)
                if byte_count > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.",
                    )
                digest.update(block)
                output.write(block)
        if b"%PDF-" not in header:
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")

        fingerprint = digest.hexdigest()
        existing = db.scalar(
            select(Document).where(
                Document.notebook_id == notebook_id,
                Document.sha256 == fingerprint,
            )
        )
        if existing is not None:
            file_path.unlink(missing_ok=True)
            return _document_response(existing)

        document = Document(
            id=document_id,
            notebook_id=notebook_id,
            filename=filename,
            storage_key=storage_key,
            sha256=fingerprint,
            status="queued",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        background_tasks.add_task(_ingest_document, document.id)
        return _document_response(document)
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        logger.exception("Could not queue uploaded PDF")
        raise HTTPException(status_code=500, detail="Could not save the uploaded PDF.") from None
    finally:
        await file.close()


def _conversation_documents(db: Session, conversation: Conversation) -> list[Document]:
    if conversation.document_id:
        document = db.get(Document, conversation.document_id)
        return [document] if document is not None else []
    documents = {document.id: document for document in conversation.documents}
    if conversation.notebook_id:
        for document in db.scalars(
            select(Document).where(Document.notebook_id == conversation.notebook_id)
        ).all():
            documents[document.id] = document
    return list(documents.values())


def _conversation_payload(db: Session, conversation: Conversation) -> dict:
    messages = []
    for message in conversation.messages:
        citations = []
        for citation in message.citations:
            chunk = citation.chunk
            document = chunk.document if chunk else None
            citations.append(
                {
                    "marker": citation.marker,
                    "chunk_id": citation.chunk_id,
                    "document_id": document.id if document else None,
                    "filename": document.filename if document else None,
                    "page_number": citation.page_number,
                    "quote": citation.quote,
                }
            )
        messages.append(
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "trace_id": message.trace_id,
                "created_at": message.created_at,
                "citations": citations,
            }
        )
    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "notebook_id": conversation.notebook_id,
        "document_id": conversation.document_id,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "documents": [
            {
                "document_id": document.id,
                "filename": document.filename,
                "page_count": document.page_count,
                "status": document.status,
            }
            for document in _conversation_documents(db, conversation)
        ],
        "messages": messages,
    }


def _require_notebook(db: Session, notebook_id: str) -> Notebook:
    notebook = db.get(Notebook, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found.")
    return notebook


@app.get("/api")
def api_info():
    return {"name": "NotebookLM Lite API", "docs": "/docs", "health": "/healthz"}


@app.get("/healthz", response_model=HealthResponse)
def health_check():
    database_status = "ok"
    ollama_status = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"
    try:
        request = urllib.request.Request(f"{settings.ollama_host.rstrip('/')}/api/tags")
        with urllib.request.urlopen(request, timeout=2):
            pass
    except (OSError, urllib.error.URLError):
        ollama_status = "unavailable"
    model_ready = {
        "ollama": True,
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "gemini": bool(os.getenv("GEMINI_API_KEY", "").strip()),
    }.get(settings.model_provider, False)
    return HealthResponse(
        status="ok" if database_status == "ok" and ollama_status == "ok" and model_ready else "degraded",
        database=database_status,
        ollama=ollama_status,
        model_provider=settings.model_provider,
        model_ready=model_ready,
        generation_model={
            "ollama": settings.generation_model,
            "openai": settings.openai_model,
            "gemini": settings.gemini_model,
        }.get(settings.model_provider, settings.generation_model),
        embedding_model=settings.embedding_model,
    )


@app.post("/notebooks", response_model=NotebookResponse, status_code=status.HTTP_201_CREATED)
def create_notebook(request: NotebookCreateRequest, db: Session = Depends(get_db)):
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Notebook title cannot be blank.")
    notebook = Notebook(title=title)
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return {"id": notebook.id, "title": notebook.title, "created_at": notebook.created_at, "document_count": 0}


@app.get("/notebooks", response_model=list[NotebookResponse])
def list_notebooks(db: Session = Depends(get_db)):
    notebooks = db.scalars(select(Notebook).order_by(Notebook.created_at.desc())).all()
    return [
        {
            "id": notebook.id,
            "title": notebook.title,
            "created_at": notebook.created_at,
            "document_count": len(notebook.documents),
        }
        for notebook in notebooks
    ]


@app.post(
    "/notebooks/{notebook_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_notebook_document(
    notebook_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _require_notebook(db, notebook_id)
    return await _save_upload(
        file=file, notebook_id=notebook_id, db=db, background_tasks=background_tasks
    )


@app.get("/notebooks/{notebook_id}/documents", response_model=list[DocumentResponse])
def list_notebook_documents(notebook_id: str, db: Session = Depends(get_db)):
    _require_notebook(db, notebook_id)
    documents = db.scalars(
        select(Document)
        .where(Document.notebook_id == notebook_id)
        .order_by(Document.created_at.desc())
    ).all()
    return [_document_response(document) for document in documents]


@app.get("/notebooks/{notebook_id}/conversations", response_model=list[dict])
def list_notebook_conversations(notebook_id: str, db: Session = Depends(get_db)):
    _require_notebook(db, notebook_id)
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.notebook_id == notebook_id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [
        {
            "conversation_id": conversation.id,
            "title": conversation.title,
            "updated_at": conversation.updated_at,
        }
        for conversation in conversations
    ]


@app.get("/documents/{document_id}/conversations", response_model=list[dict])
def list_document_conversations(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.document_id == document_id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [
        {
            "conversation_id": conversation.id,
            "title": conversation.title,
            "updated_at": conversation.updated_at,
        }
        for conversation in conversations
    ]


@app.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf_legacy(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Compatibility upload route; new clients should upload to a notebook."""
    return await _save_upload(file=file, notebook_id=None, db=db, background_tasks=background_tasks)


@app.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _document_response(document)


@app.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    file_path = UPLOAD_DIR / Path(document.storage_key).name if document.storage_key else None
    db.delete(document)
    db.commit()
    if file_path is not None:
        file_path.unlink(missing_ok=True)
    return None


@app.get("/documents/{document_id}/pages/{page_number}", response_model=PageResponse)
def get_document_page(document_id: str, page_number: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if page_number < 1 or page_number > document.page_count:
        raise HTTPException(status_code=404, detail="Page not found in this document.")
    chunks = db.scalars(
        select(Chunk)
        .where(Chunk.document_id == document_id, Chunk.page_number == page_number)
        .order_by(Chunk.chunk_index)
    ).all()
    return {
        "document_id": document.id,
        "filename": document.filename,
        "page_number": page_number,
        "page_count": document.page_count,
        "text": "\n\n".join(chunk.text for chunk in chunks),
    }


@app.post("/conversations", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_conversation(request: ConversationCreateRequest, db: Session = Depends(get_db)):
    title = request.title.strip() or "New conversation"
    document = db.get(Document, request.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if request.notebook_id:
        notebook = _require_notebook(db, request.notebook_id)
        if document is not None and document.notebook_id != notebook.id:
            raise HTTPException(status_code=400, detail="Document belongs to a different notebook.")
    notebook_id = document.notebook_id
    conversation = Conversation(
        title=title, notebook_id=notebook_id, document_id=document.id
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "notebook_id": conversation.notebook_id,
        "document_id": conversation.document_id,
        "created_at": conversation.created_at,
    }


@app.post("/conversations/{conversation_id}/documents/{document_id}")
def attach_document_to_conversation(
    conversation_id: str, document_id: str, db: Session = Depends(get_db)
):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if conversation.notebook_id and document.notebook_id != conversation.notebook_id:
        raise HTTPException(status_code=400, detail="Document belongs to a different notebook.")
    if conversation.document_id:
        if conversation.document_id != document.id:
            raise HTTPException(status_code=400, detail="This conversation is limited to its document.")
        return {"conversation_id": conversation.id, "document_id": document.id}
    conversation.document_id = document.id
    conversation.notebook_id = document.notebook_id
    db.commit()
    return {"conversation_id": conversation.id, "document_id": document.id}


@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return _conversation_payload(db, conversation)


@app.post("/conversations/{conversation_id}/messages", response_model=dict)
def send_conversation_message(
    conversation_id: str,
    request: ConversationMessageRequest,
    db: Session = Depends(get_db),
):
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content cannot be blank.")
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    documents = _conversation_documents(db, conversation)
    if not documents:
        raise HTTPException(status_code=400, detail="Attach a document before asking a question.")

    history = [
        {"role": message.role, "content": message.content}
        for message in conversation.messages[-8:]
    ]
    user_message = Message(conversation_id=conversation.id, role="user", content=content)
    db.add(user_message)
    if conversation.title == "New conversation":
        conversation.title = content[:252].rstrip() + ("…" if len(content) > 252 else "")
    db.commit()
    db.refresh(user_message)

    result = answer_from_documents(
        db=db,
        question=content,
        document_ids=[document.id for document in documents],
        feature="conversation_qa",
        conversation_history=history,
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        trace_id=result.get("trace_id"),
    )
    db.add(assistant_message)
    db.flush()
    _persist_citations(db, assistant_message, result)
    conversation.updated_at = assistant_message.created_at
    db.commit()
    db.refresh(assistant_message)

    return {
        "conversation_id": conversation.id,
        "user_message": {
            "id": user_message.id,
            "role": user_message.role,
            "content": user_message.content,
            "created_at": user_message.created_at,
        },
        "assistant_message": {
            "id": assistant_message.id,
            "role": assistant_message.role,
            "content": assistant_message.content,
            "trace_id": assistant_message.trace_id,
            "created_at": assistant_message.created_at,
        },
        "answer": result["answer"],
        "trace_id": result.get("trace_id"),
        "sources": [source_response(source) for source in result.get("sources", [])],
        "citation_validation": result["validation"],
        "generation_attempts": len(result.get("attempts", [])),
        "status": result.get("status", "success"),
    }


def _ask_documents(
    *, question: str, document_ids: list[str], db: Session, feature: str = "direct_qa"
) -> dict:
    clean_question = question.strip()
    if not clean_question:
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    if not document_ids:
        raise HTTPException(status_code=400, detail="No documents are available in this scope.")
    unique_ids = list(dict.fromkeys(document_ids))
    documents = db.scalars(select(Document.id).where(Document.id.in_(unique_ids))).all()
    if len(documents) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more documents were not found.")
    result = answer_from_documents(
        db=db,
        question=clean_question,
        document_ids=unique_ids,
        feature=feature,
    )
    return _answer_response(clean_question, result)


@app.post("/ask", response_model=AnswerResponse)
def ask_question(request: AskRequest, db: Session = Depends(get_db)):
    supplied_scopes = sum(
        [bool(request.document_id), bool(request.document_ids), bool(request.notebook_id)]
    )
    if supplied_scopes != 1:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of document_id, document_ids, or notebook_id.",
        )
    if request.notebook_id:
        _require_notebook(db, request.notebook_id)
        document_ids = db.scalars(
            select(Document.id).where(Document.notebook_id == request.notebook_id)
        ).all()
    elif request.document_id:
        document_ids = [request.document_id]
    else:
        document_ids = request.document_ids or []
    return _ask_documents(question=request.question, document_ids=document_ids, db=db)


@app.post("/notebooks/{notebook_id}/ask", response_model=AnswerResponse)
def ask_notebook(
    notebook_id: str,
    request: NotebookAskRequest,
    db: Session = Depends(get_db),
):
    _require_notebook(db, notebook_id)
    document_ids = db.scalars(
        select(Document.id).where(Document.notebook_id == notebook_id)
    ).all()
    return _ask_documents(
        question=request.question,
        document_ids=document_ids,
        db=db,
        feature="notebook_qa",
    )


@app.get("/model-calls", response_model=list[ModelCallResponse])
def list_model_calls(limit: int = 100, db: Session = Depends(get_db)):
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500.")
    return db.scalars(select(ModelCall).order_by(ModelCall.created_at.desc()).limit(limit)).all()


@app.get("/traces/{trace_id}", response_model=list[ModelCallResponse])
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    calls = db.scalars(
        select(ModelCall)
        .where(ModelCall.trace_id == trace_id)
        .order_by(ModelCall.attempt_number)
    ).all()
    if not calls:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return calls


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
