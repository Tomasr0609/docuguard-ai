"""FastAPI application — document upload, status, and report endpoints."""
import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from sqlalchemy import select

from backend.db.session import init_db, async_session_factory
from backend.db.models import Document, Finding, ProcessingStatus
from backend.processing.pipeline import process_document
from backend.config import settings

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="DocuGuard AI Lite API",
    description="Document compliance verification platform with multi-agent RAG pipeline",
    version="1.0.0",
)

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup() -> None:
    await init_db()
    logger.info("startup: DB initialized, logging configured at %s", settings.log_level)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
) -> dict:
    """Upload a document and trigger processing in the background."""
    if file.size and file.size > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.max_file_size_mb}MB.")

    contents = await file.read()
    doc_id = str(uuid.uuid4())[:8]
    ext = Path(file.filename or "doc").suffix.lower() or ".bin"
    dest = UPLOAD_DIR / f"{doc_id}{ext}"
    dest.write_bytes(contents)

    async with async_session_factory() as session:
        doc = Document(
            doc_id=doc_id,
            filename=file.filename or "document.bin",
            file_type=ext.lstrip("."),
            status=ProcessingStatus.pending,
        )
        session.add(doc)
        await session.commit()

    # Schedule the pipeline via asyncio.create_task instead of BackgroundTasks
    # to ensure async functions run reliably in the event loop.
    task = asyncio.create_task(process_document(doc_id, dest))
    task.add_done_callback(
        lambda t: logger.error(
            "Unhandled exception in process_document: %s", t.exception()
        ) if t.exception() else None
    )

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "status": "pending",
        "message": "Document uploaded. Processing in background.",
    }


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str) -> dict:
    """Get document status and report."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Document).where(Document.doc_id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        result = await session.execute(
            select(Finding).where(Finding.document_id == doc.id)
        )
        findings = result.scalars().all()

    return {
        "doc_id": doc.doc_id,
        "filename": doc.filename,
        "status": doc.status.value if doc.status else "unknown",
        "doc_type": doc.doc_type.value if doc.doc_type else None,
        "risk_level": doc.risk_level.value if doc.risk_level else None,
        "risk_score": doc.risk_score,
        "executive_summary": doc.executive_summary,
        "processing_time_ms": doc.processing_time_ms,
        "total_cost_usd": doc.total_cost_usd,
        "findings": [
            {
                "type": f.finding_type,
                "severity": f.severity.value,
                "description": f.description,
                "source_snippet": f.source_snippet,
                "reference_clause": f.reference_clause,
                "agent_name": f.agent_name,
            }
            for f in findings
        ],
    }


@app.get("/documents")
async def list_documents() -> list[dict]:
    """List all processed documents."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Document).order_by(Document.created_at.desc()).limit(50)
        )
        docs = result.scalars().all()

    return [
        {
            "doc_id": d.doc_id,
            "filename": d.filename,
            "status": d.status.value if d.status else "unknown",
            "doc_type": d.doc_type.value if d.doc_type else None,
            "risk_level": d.risk_level.value if d.risk_level else None,
            "risk_score": d.risk_score,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]
