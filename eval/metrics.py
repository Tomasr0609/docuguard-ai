"""Evaluation metrics for DocuGuard AI Lite.

Computes structural metrics (finding recall, precision, severity accuracy)
without requiring LLM calls. Ragas metrics require an API key.
"""
from typing import Any


def compute_finding_recall(
    ground_truth_findings: list[dict],
    detected_findings: list[dict],
) -> float:
    """What fraction of expected findings were detected by the pipeline?

    Matching is by finding type. A finding is considered 'detected' if
    a pipeline finding with the same type exists.
    """
    if not ground_truth_findings:
        return 1.0  # no findings to detect = perfect score

    expected_types = {f.get("type") for f in ground_truth_findings if f.get("type")}
    detected_types = {f.get("type") for f in detected_findings if f.get("type")}

    if not expected_types:
        return 1.0

    hits = expected_types & detected_types
    return round(len(hits) / len(expected_types), 4)


def compute_finding_precision(
    ground_truth_findings: list[dict],
    detected_findings: list[dict],
) -> float:
    """What fraction of detected findings match expected findings."""
    if not detected_findings:
        return 1.0  # no spurious findings

    expected_types = {f.get("type") for f in ground_truth_findings if f.get("type")}
    detected_types = {f.get("type") for f in detected_findings if f.get("type")}

    if not detected_types:
        return 1.0

    hits = expected_types & detected_types
    return round(len(hits) / len(detected_types), 4)


def compute_severity_accuracy(ground_truth_findings: list[dict], detected_findings: list[dict]) -> float:
    """Of findings that were correctly detected, what fraction had correct severity?"""
    gt_by_type = {f.get("type"): f.get("severity") for f in ground_truth_findings if f.get("type")}
    detected_by_type = {f.get("type"): f.get("severity") for f in detected_findings if f.get("type")}

    correct = 0
    total = 0
    for ftype, gt_sev in gt_by_type.items():
        if ftype in detected_by_type:
            total += 1
            if detected_by_type[ftype] == gt_sev:
                correct += 1

    return round(correct / total, 4) if total > 0 else 1.0


def compute_risk_level_accuracy(gt_risk: str | None, detected_risk: str | None) -> float:
    """1.0 if risk levels match, 0.0 otherwise."""
    gt = gt_risk or "none"
    detected = detected_risk or "none"
    return 1.0 if gt == detected else 0.0


def compute_extraction_accuracy(gt_doc: dict, pipeline_result: dict) -> float:
    """Simple extraction accuracy: check if doc_type was detected correctly."""
    gt_type = gt_doc.get("doc_type", "unknown")
    detected_type = pipeline_result.get("doc_type", "unknown")
    return 1.0 if gt_type == detected_type else 0.0


def compute_all_metrics(
    ground_truth: list[dict],
    pipeline_results: list[dict],
) -> dict[str, Any]:
    """Compute all evaluation metrics across the dataset.

    Args:
        ground_truth: list of ground truth records from ground_truth.jsonl
        pipeline_results: list of pipeline output dicts (one per doc, same order)

    Returns:
        dict with aggregate metrics
    """
    total_finding_recall = 0.0
    total_finding_precision = 0.0
    total_severity_accuracy = 0.0
    total_risk_accuracy = 0.0
    total_extraction_accuracy = 0.0
    doc_count = min(len(ground_truth), len(pipeline_results))

    if doc_count == 0:
        return {
            "status": "no_data",
            "n_docs": 0,
            "finding_recall": 0.0,
            "finding_precision": 0.0,
            "severity_accuracy": 0.0,
            "risk_level_accuracy": 0.0,
            "extraction_accuracy": 0.0,
        }

    for i in range(doc_count):
        gt = ground_truth[i]
        pr = pipeline_results[i]

        total_finding_recall += compute_finding_recall(
            gt.get("findings", []), pr.get("findings", [])
        )
        total_finding_precision += compute_finding_precision(
            gt.get("findings", []), pr.get("findings", [])
        )
        total_severity_accuracy += compute_severity_accuracy(
            gt.get("findings", []), pr.get("findings", [])
        )
        total_risk_accuracy += compute_risk_level_accuracy(
            gt.get("risk_level"), pr.get("risk_level")
        )
        total_extraction_accuracy += compute_extraction_accuracy(gt, pr)

    return {
        "status": "ok",
        "n_docs": doc_count,
        "finding_recall": round(total_finding_recall / doc_count, 4),
        "finding_precision": round(total_finding_precision / doc_count, 4),
        "severity_accuracy": round(total_severity_accuracy / doc_count, 4),
        "risk_level_accuracy": round(total_risk_accuracy / doc_count, 4),
        "extraction_accuracy": round(total_extraction_accuracy / doc_count, 4),
    }
