"""Document processing pipeline: ingestion -> agent graph -> database persistence."""
import logging
import time
from pathlib import Path

from sqlalchemy import select

from backend.db.session import async_session_factory
from backend.db.models import Document, Finding, ProcessingStatus, DocType, FileFormat, RiskLevel, FindingSeverity
from backend.ingestion.ocr import extract_text_from_image, extract_text_from_scanned_pdf
from backend.ingestion.pdf_parser import extract_text_from_native_pdf, is_scanned_pdf, get_page_count
from backend.agents.graph import compiled_graph
from backend.agents.state import AgentState

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def process_document(doc_id: str, file_path: Path) -> None:
    """Full pipeline: extract text -> run agent graph -> persist results."""
    start_time = time.time()
    async with async_session_factory() as session:
        try:
            result = await session.execute(select(Document).where(Document.doc_id == doc_id))
            db_doc = result.scalar_one_or_none()
            if db_doc is None:
                logger.error("process_document: Document with doc_id=%s not found in DB", doc_id)
                return

            db_doc.status = ProcessingStatus.processing
            await session.commit()
            logger.info("process_document: doc_id=%s status=processing", doc_id)

            # 1. Extract text based on file type
            ext = file_path.suffix.lower()
            raw_text = ""
            file_format = FileFormat.text
            doc_type_str = _detect_doc_type_from_filename(file_path.name)

            if ext == ".pdf":
                if is_scanned_pdf(str(file_path)):
                    raw_text = extract_text_from_scanned_pdf(str(file_path))
                    file_format = FileFormat.scanned
                else:
                    raw_text = extract_text_from_native_pdf(str(file_path))
                    file_format = FileFormat.native_pdf
            elif ext in (".png", ".jpg", ".jpeg"):
                raw_text = extract_text_from_image(str(file_path))
                file_format = FileFormat.image
            elif ext == ".txt":
                raw_text = file_path.read_text(encoding="utf-8")
                file_format = FileFormat.text

            db_doc.extracted_text = raw_text
            db_doc.format = file_format
            await session.commit()

            # 2. Run agent graph
            initial_state: AgentState = {
                "doc_id": doc_id,
                "raw_text": raw_text,
                "doc_type": doc_type_str,
                "extracted_info": None,
                "findings": [],
                "risk_level": None,
                "risk_score": None,
                "executive_summary": None,
                "errors": [],
            }

            result = await compiled_graph.ainvoke(initial_state)

            # 3. Persist results
            db_doc.doc_type = DocType(result.get("doc_type", doc_type_str)) if result.get("doc_type") in ("contract", "nda", "invoice") else None
            db_doc.risk_level = RiskLevel(result["risk_level"]) if result.get("risk_level") and result["risk_level"] in ("low", "medium", "high", "none") else None
            db_doc.risk_score = result.get("risk_score")
            db_doc.executive_summary = result.get("executive_summary")
            db_doc.status = ProcessingStatus.completed

            # Save findings
            for f_data in result.get("findings", []):
                finding = Finding(
                    document_id=db_doc.id,
                    finding_type=f_data.get("type", "unknown"),
                    severity=FindingSeverity(f_data.get("severity", "medium")),
                    description=f_data.get("description", ""),
                    source_page=f_data.get("source_page"),
                    source_line=f_data.get("source_line"),
                    source_snippet=f_data.get("source_snippet"),
                    reference_clause=f_data.get("reference_clause"),
                    agent_name=f_data.get("agent_name", "unknown"),
                )
                session.add(finding)

            if result.get("errors"):
                db_doc.status = ProcessingStatus.failed

            elapsed = int((time.time() - start_time) * 1000)
            db_doc.processing_time_ms = elapsed
            await session.commit()
            logger.info("process_document: doc_id=%s completed in %d ms", doc_id, elapsed)

        except Exception as e:
            logger.exception("process_document: doc_id=%s failed: %s", doc_id, e)
            try:
                db_doc.status = ProcessingStatus.failed
                db_doc.executive_summary = f"Pipeline error: {e}"
                await session.commit()
            except Exception as commit_err:
                logger.exception("process_document: failed to persist failure status for doc_id=%s: %s", doc_id, commit_err)


def _detect_doc_type_from_filename(filename: str) -> str:
    name = filename.lower()
    if "factura" in name or "invoice" in name:
        return "invoice"
    if "nda" in name or "confidencialidad" in name or "confidentiality" in name:
        return "nda"
    if "contrato" in name or "contract" in name or "servicio" in name:
        return "contract"
    return "unknown"
