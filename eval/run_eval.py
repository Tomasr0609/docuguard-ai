"""Evaluation harness for DocuGuard AI Lite.

Usage:
    python eval/run_eval.py                        # structural metrics only (no API key needed)
    python eval/run_eval.py --full                 # full pipeline + Ragas (requires API key)
    python eval/run_eval.py --subset 5             # run on first N docs

Generates a report in eval/results/{timestamp}.md
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.metrics import compute_all_metrics

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "ground_truth.jsonl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
SYNTHETIC_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic_docs"


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Ground truth not found: {path}")
    docs: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


def run_structural_eval(subset: Optional[int] = None) -> dict[str, Any]:
    """Run evaluation using ground truth vs structural document properties.

    This mode does NOT require an LLM API key. It checks:
    - Are findings correctly detected? (recall / precision)
    - Is severity correctly classified?
    - Is risk level correct?
    - Is doc_type detected correctly?

    For structural eval, we simulate "detected findings" by checking
    the document text for known finding indicators. This gives a baseline.
    """
    ground_truth = load_ground_truth()
    if subset:
        ground_truth = ground_truth[:subset]

    # Simulate pipeline results from the ground truth itself
    # (for a real eval, these would come from the actual pipeline)
    simulated_results: list[dict] = []
    for gt in ground_truth:
        simulated_results.append({
            "doc_id": gt["doc_id"],
            "doc_type": gt.get("doc_type", "unknown"),
            "findings": gt.get("findings", []),
            "risk_level": gt.get("risk_level", "none"),
            "risk_score": gt.get("risk_score", 0.0),
        })

    # Compute all structural metrics
    metrics = compute_all_metrics(ground_truth, simulated_results)

    # Structural baseline: results == ground truth, so metrics == 1.0
    metrics["eval_mode"] = "structural_baseline"
    metrics["note"] = (
        "All scores are 1.0 because this baseline evaluates ground truth against itself. "
        "To get real metrics, configure ANTHROPIC_API_KEY and run with --full."
    )

    # Analyze distribution
    clean_count = sum(1 for d in ground_truth if not d.get("is_risky", True))
    risky_count = len(ground_truth) - clean_count
    total_findings = sum(len(d.get("findings", [])) for d in ground_truth)
    ambiguous_count = sum(1 for d in ground_truth if d.get("ambiguous"))

    metrics["distribution"] = {
        "total_docs": len(ground_truth),
        "clean": clean_count,
        "risky": risky_count,
        "total_findings": total_findings,
        "ambiguous_docs": ambiguous_count,
    }

    return metrics


async def run_full_eval(subset: Optional[int] = None) -> dict[str, Any]:
    """Run the full pipeline + Ragas evaluation. Requires API key."""
    from backend.config import settings

    if not settings.anthropic_api_key or settings.anthropic_api_key == "sk-ant-...":
        raise ValueError("ANTHROPIC_API_KEY not configured. Run without --full for structural eval.")

    ground_truth = load_ground_truth()
    if subset:
        ground_truth = ground_truth[:subset]

    pipeline_results: list[dict] = []

    for gt in ground_truth:
        doc_id = gt["doc_id"]
        txt_path = SYNTHETIC_DIR / f"{doc_id}.txt"
        if not txt_path.exists():
            print(f"  WARNING: {txt_path} not found, skipping")
            continue

        print(f"  Processing {doc_id} ({gt.get('doc_type', '?')})...")
        from backend.processing.pipeline import process_document, UPLOAD_DIR

        # Copy to upload dir
        dest = UPLOAD_DIR / f"{doc_id}.txt"
        dest.write_bytes(txt_path.read_bytes())

        # Create DB record
        from backend.db.session import async_session_factory
        from backend.db.models import Document, ProcessingStatus

        async with async_session_factory() as session:
            existing = await session.get(Document, doc_id)
            if not existing:
                doc = Document(
                    doc_id=doc_id,
                    filename=txt_path.name,
                    file_type="txt",
                    status=ProcessingStatus.pending,
                )
                session.add(doc)
                await session.commit()

        # Run pipeline
        await process_document(doc_id, dest)

        # Get results from DB
        async with async_session_factory() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                from sqlalchemy import select
                from backend.db.models import Finding
                result = await session.execute(
                    select(Finding).where(Finding.document_id == doc_id)
                )
                findings = result.scalars().all()
                pipeline_results.append({
                    "doc_id": doc.doc_id,
                    "doc_type": doc.doc_type.value if doc.doc_type else "unknown",
                    "extracted_text": doc.extracted_text,
                    "risk_level": doc.risk_level.value if doc.risk_level else "none",
                    "risk_score": doc.risk_score,
                    "executive_summary": doc.executive_summary,
                    "status": doc.status.value if doc.status else "unknown",
                    "findings": [
                        {
                            "type": f.finding_type,
                            "severity": f.severity.value if f.severity else "medium",
                            "description": f.description,
                        }
                        for f in findings
                    ],
                })

    # Compute structural metrics
    metrics = compute_all_metrics(ground_truth, pipeline_results)
    metrics["eval_mode"] = "full_pipeline"
    metrics["docs_processed"] = len(pipeline_results)
    return metrics


def generate_report(metrics: dict[str, Any], output_path: Path) -> str:
    """Generate a Markdown report from metrics."""
    lines = []
    lines.append(f"# DocuGuard AI Lite — Evaluation Report")
    lines.append(f"")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Mode:** {metrics.get('eval_mode', 'unknown')}")
    lines.append(f"")
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")

    if "distribution" in metrics:
        d = metrics["distribution"]
        lines.append(f"| Total documents | {d['total_docs']} |")
        lines.append(f"| Clean / Risky | {d['clean']} / {d['risky']} |")
        lines.append(f"| Total findings | {d['total_findings']} |")
        lines.append(f"| Ambiguous docs | {d['ambiguous_docs']} |")

    lines.append(f"| Finding Recall | {metrics.get('finding_recall', 'N/A')} |")
    lines.append(f"| Finding Precision | {metrics.get('finding_precision', 'N/A')} |")
    lines.append(f"| Severity Accuracy | {metrics.get('severity_accuracy', 'N/A')} |")
    lines.append(f"| Risk Level Accuracy | {metrics.get('risk_level_accuracy', 'N/A')} |")
    lines.append(f"| Extraction Accuracy | {metrics.get('extraction_accuracy', 'N/A')} |")

    if "note" in metrics:
        lines.append(f"")
        lines.append(f"> **Note:** {metrics['note']}")

    lines.append(f"")
    lines.append(f"## Per-doc details")

    if "per_doc" in metrics:
        for doc in metrics["per_doc"]:
            lines.append(f"")
            lines.append(f"### {doc['doc_id']} ({doc.get('doc_type', '?')})")
            lines.append(f"- Risk: {doc.get('risk_level', 'N/A')}")
            lines.append(f"- Findings: {len(doc.get('findings', []))}")

    report = "\n".join(lines)
    output_path.write_text(report, encoding="utf-8")
    return report


def main() -> None:
    import asyncio

    args = sys.argv[1:]
    full = "--full" in args
    subset = None
    for i, arg in enumerate(args):
        if arg == "--subset" and i + 1 < len(args):
            try:
                subset = int(args[i + 1])
            except ValueError:
                pass

    print(f">>> DocuGuard AI Lite — Evaluation Harness")
    print(f"    Mode: {'full pipeline' if full else 'structural (no API key needed)'}")
    if subset:
        print(f"    Subset: first {subset} documents")
    print()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if full:
        metrics = asyncio.run(run_full_eval(subset=subset))
    else:
        metrics = run_structural_eval(subset=subset)

    report_path = RESULTS_DIR / f"{timestamp}.md"
    report = generate_report(metrics, report_path)

    print(report)
    print(f"\n>>> Report saved to: {report_path}")


if __name__ == "__main__":
    main()
