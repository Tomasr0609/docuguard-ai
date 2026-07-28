import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class DocType(str, enum.Enum):
    contract = "contract"
    nda = "nda"
    invoice = "invoice"


class FileFormat(str, enum.Enum):
    native_pdf = "native_pdf"
    scanned = "scanned"
    image = "image"
    text = "text"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    none_ = "none"


class FindingSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(100), unique=True, nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(10), nullable=False)
    doc_type = Column(SAEnum(DocType), nullable=True)
    format = Column(SAEnum(FileFormat), nullable=True)
    status = Column(SAEnum(ProcessingStatus), default=ProcessingStatus.pending, nullable=False)
    extracted_text = Column(Text, nullable=True)
    risk_level = Column(SAEnum(RiskLevel), nullable=True)
    risk_score = Column(Float, nullable=True)
    executive_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    processing_time_ms = Column(Integer, nullable=True)
    total_cost_usd = Column(Float, nullable=True)
    processing_errors = Column(Text, nullable=True)

    findings = relationship("Finding", back_populates="document", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    finding_type = Column(String(100), nullable=False)
    severity = Column(SAEnum(FindingSeverity), nullable=False)
    description = Column(Text, nullable=False)
    source_page = Column(Integer, nullable=True)
    source_line = Column(Integer, nullable=True)
    source_snippet = Column(Text, nullable=True)
    reference_clause = Column(Text, nullable=True)
    agent_name = Column(String(100), nullable=False)

    document = relationship("Document", back_populates="findings")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    num_docs = Column(Integer, nullable=False)
    faithfulness = Column(Float, nullable=True)
    context_precision = Column(Float, nullable=True)
    context_recall = Column(Float, nullable=True)
    extraction_accuracy = Column(Float, nullable=True)
    avg_cost_per_doc = Column(Float, nullable=True)
    avg_latency_ms = Column(Float, nullable=True)
    report_path = Column(String(500), nullable=True)
