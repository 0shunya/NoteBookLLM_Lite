from pathlib import Path
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import Base, engine, get_db
from app.db.models import (
    Chunk,
    Conversation,
    Document,
    Message,
)
from app.services.embedding_indexer import embed_document_chunks
from app.services.generation_service import generate_answer
from app.services.hybrid_search import hybrid_search_chunks
from app.services.model_call_service import (
    create_trace_id,
    record_model_call,
)
from app.services.pdf_parser import extract_pages
from app.services.source_builder import build_sources


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NotebookLM Lite",
    description="A local RAG-based document question-answering API.",
    version="1.0.0",
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Development-time table creation.
# Later, replace this with Alembic migrations.
Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    """
    Request body for the /ask endpoint.
    """

    question: str
    document_id: str


class ConversationCreateRequest(BaseModel):
    """
    Request body for creating a conversation.
    """

    title: str = "New conversation"

class ConversationMessageRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Root / health endpoint
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    """
    Basic API health check.
    """

    return {
        "message": "NotebookLM Lite API is running"
    }


# ---------------------------------------------------------------------------
# Document upload + ingestion
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload and completely ingest a PDF.

    Pipeline:

        PDF
         ↓
        Save file
         ↓
        Extract pages
         ↓
        Create chunks
         ↓
        Store document + chunks
         ↓
        Generate embeddings
         ↓
        Store vectors
         ↓
        READY
    """

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported.",
        )

    document_id = str(uuid.uuid4())

    file_path = UPLOAD_DIR / f"{document_id}.pdf"

    try:
        # ---------------------------------------------------------------
        # Save PDF
        # ---------------------------------------------------------------

        with file_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)

        # ---------------------------------------------------------------
        # Parse PDF + create chunks
        # ---------------------------------------------------------------

        chunks = extract_pages(
            file_path=str(file_path),
            document_id=document_id,
        )

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No readable text was found in the PDF.",
            )

        total_pages = len(
            {
                chunk["page_number"]
                for chunk in chunks
            }
        )

        # ---------------------------------------------------------------
        # Store document
        # ---------------------------------------------------------------

        document = Document(
            id=document_id,
            filename=file.filename or "unknown.pdf",
            page_count=total_pages,
        )

        db.add(document)

        # ---------------------------------------------------------------
        # Store chunks
        # ---------------------------------------------------------------

        for chunk_data in chunks:
            db.add(
                Chunk(
                    document_id=document_id,
                    page_number=chunk_data["page_number"],
                    text=chunk_data["text"],
                )
            )

        db.commit()

        # ---------------------------------------------------------------
        # Generate embeddings
        # ---------------------------------------------------------------

        embedded_count = embed_document_chunks(
            db=db,
            document_id=document_id,
        )

        return {
            "document_id": document_id,
            "filename": file.filename,
            "total_pages": total_pages,
            "total_chunks": len(chunks),
            "total_embeddings": embedded_count,
            "status": "ready",
            "message": "Document uploaded and indexed successfully.",
        }

    except HTTPException:
        db.rollback()

        if file_path.exists():
            file_path.unlink()

        raise

    except Exception as exc:
        db.rollback()

        if file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=500,
            detail=f"Document ingestion failed: {str(exc)}",
        ) from exc


# ---------------------------------------------------------------------------
# Conversation creation
# ---------------------------------------------------------------------------

@app.post("/conversations")
def create_conversation(
    request: ConversationCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new conversation.
    """

    title = request.title.strip()

    if not title:
        title = "New conversation"

    conversation = Conversation(
        id=str(uuid.uuid4()),
        title=title,
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
    }


# ---------------------------------------------------------------------------
# Attach document to conversation
# ---------------------------------------------------------------------------

@app.post(
    "/conversations/{conversation_id}/documents/{document_id}"
)
def attach_document_to_conversation(
    conversation_id: str,
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Attach an existing document to a conversation.

    A conversation can contain multiple documents.
    """

    conversation = db.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    document = db.get(
        Document,
        document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    # Avoid creating duplicate relationships.
    if document not in conversation.documents:
        conversation.documents.append(document)
        db.commit()

    return {
        "conversation_id": conversation.id,
        "document_id": document.id,
        "message": "Document attached to conversation.",
    }


# ---------------------------------------------------------------------------
# Get conversation
# ---------------------------------------------------------------------------

@app.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    """
    Return conversation metadata, attached documents,
    and stored messages.
    """

    conversation = db.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "documents": [
            {
                "document_id": document.id,
                "filename": document.filename,
                "page_count": document.page_count,
            }
            for document in conversation.documents
        ],
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in conversation.messages
        ],
    }


@app.post("/conversations/{conversation_id}/messages")
def send_conversation_message(
    conversation_id: str,
    request: ConversationMessageRequest,
    db: Session = Depends(get_db),
):
    content = request.content.strip()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Message content cannot be empty.",
        )

    # ---------------------------------------------------------
    # 1. Verify conversation
    # ---------------------------------------------------------
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    # ---------------------------------------------------------
    # 2. Get documents attached to this conversation
    # ---------------------------------------------------------
    documents = conversation.documents

    if not documents:
        raise HTTPException(
            status_code=400,
            detail="No documents are attached to this conversation.",
        )

    document_ids = [document.id for document in documents]

    # ---------------------------------------------------------
    # 3. Save the user's message
    # ---------------------------------------------------------
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )

    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # ---------------------------------------------------------
    # 4. Retrieve relevant chunks from ALL attached documents
    # ---------------------------------------------------------
    search_results = hybrid_search_chunks(
        db=db,
        query=content,
        document_ids=document_ids,
        limit=3,
        candidate_limit=10,
    )

    if not search_results:
        assistant_content = (
            "I could not find relevant information in the "
            "documents attached to this conversation."
        )

        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_content,
        )

        db.add(assistant_message)
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
                "created_at": assistant_message.created_at,
            },
            "answer": assistant_content,
            "sources": [],
            "citation_validation": {
                "valid": True,
                "cited_source_ids": [],
                "invalid_source_ids": [],
                "uncited_sentences": [],
            },
            "generation_attempts": 0,
        }

    # ---------------------------------------------------------
    # 5. Convert retrieved chunks into numbered sources
    # ---------------------------------------------------------
    sources = build_sources(search_results)


    # ---------------------------------------------------------
    # 6. Build conversation history
    #
    # The current user message is excluded because it is already
    # passed separately as the current question.
    #
    # Previous messages help the model understand references such
    # as "it", "those", "that project", etc.
    #
    # IMPORTANT:
    # Conversation history is context only.
    # Retrieved document sources remain the factual evidence.
    # ---------------------------------------------------------
    conversation_history = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in conversation.messages
        if message.id != user_message.id
    ]


    # ---------------------------------------------------------
    # 7. Generate grounded answer
    # ---------------------------------------------------------
    trace_id = create_trace_id()

    generation_result = generate_answer(
        question=content,
        sources=sources,
        conversation_history=conversation_history,
    )

    # ---------------------------------------------------------
    # 7. Save assistant response
    # ---------------------------------------------------------
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=generation_result["answer"],
    )

    db.add(assistant_message)

    db.commit()
    db.refresh(assistant_message)


    model_response = generation_result["model_response"]

    record_model_call(
        db=db,
        trace_id=trace_id,
        build="notebooklm-lite",
        feature="conversation_qa",
        provider=model_response.provider,
        model=model_response.model,
        prompt_version="v1",
        input_tokens=model_response.input_tokens,
        output_tokens=model_response.output_tokens,
        cost_usd=0.0,
        latency_ms=model_response.latency_ms,
        status="success",
    )

    # ---------------------------------------------------------
    # 8. Return complete response
    # ---------------------------------------------------------
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
            "created_at": assistant_message.created_at,
        },
        "answer": generation_result["answer"],
        "sources": [
            {
                "id": source.source_id,
                "chunk_id": source.chunk_id,
                "document_id": source.document_id,
                "filename": source.filename,
                "page_number": source.page_number,
            }
            for source in sources
        ],
        "citation_validation": generation_result["validation"],
        "generation_attempts": generation_result["attempts"],
    }

# ---------------------------------------------------------------------------
# Question answering
# ---------------------------------------------------------------------------

@app.post("/ask")
def ask_question(
    request: AskRequest,
    db: Session = Depends(get_db),
):
    """
    Answer a question using the selected document.

    This endpoint remains available for direct document-based
    questions while conversation messaging is being added.
    """

    question = request.question.strip()
    document_id = request.document_id.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    if not document_id:
        raise HTTPException(
            status_code=400,
            detail="document_id cannot be empty.",
        )

    document = db.get(
        Document,
        document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    # ---------------------------------------------------------------
    # Hybrid retrieval
    # ---------------------------------------------------------------

    search_results = hybrid_search_chunks(
        db=db,
        query=question,
        document_id=document_id,
        limit=3,
        candidate_limit=10,
    )

    if not search_results:
        return {
            "question": question,
            "document_id": document_id,
            "answer": (
                "I could not find relevant information "
                "in the selected document."
            ),
            "sources": [],
            "citation_validation": {
                "valid": True,
                "cited_source_ids": [],
                "invalid_source_ids": [],
                "uncited_sentences": [],
            },
            "generation_attempts": 0,
        }

    # ---------------------------------------------------------------
    # Build sources
    # ---------------------------------------------------------------

    sources = build_sources(search_results)

    # ---------------------------------------------------------------
    # Generate grounded answer
    # ---------------------------------------------------------------

    trace_id = create_trace_id()

    generation_result = generate_answer(
        question=question,
        sources=sources,
    )

    model_response = generation_result["model_response"]

    record_model_call(
        db=db,
        trace_id=trace_id,
        build="notebooklm-lite",
        feature="direct_qa",
        provider=model_response.provider,
        model=model_response.model,
        prompt_version="v1",
        input_tokens=model_response.input_tokens,
        output_tokens=model_response.output_tokens,
        cost_usd=0.0,
        latency_ms=model_response.latency_ms,
        status="success",
    )

    return {
        "question": question,
        "document_id": document_id,
        "answer": generation_result["answer"],
        "sources": [
            {
                "id": source.source_id,
                "chunk_id": source.chunk_id,
                "document_id": source.document_id,
                "filename": source.filename,
                "page_number": source.page_number,
            }
            for source in sources
        ],
        "citation_validation": generation_result["validation"],
        "generation_attempts": generation_result["attempts"],
    }