"""Structured local tracing for LLM calls.

Every agent LLM call is logged as a JSON line in logs/traces.jsonl.
This replaces what Langfuse would do in production.
"""
import json
import time
from pathlib import Path
from typing import Optional

TRACES_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "traces.jsonl"

# Cost per 1K tokens (USD) — approximate
COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "anthropic": {"input": 0.003, "output": 0.015},
    "ollama": {"input": 0.0, "output": 0.0},
}


def estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_1K_TOKENS.get(provider, COST_PER_1K_TOKENS["anthropic"])
    return round((input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"], 6)


def log_llm_call(
    agent_name: str,
    task_type: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    doc_id: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> dict:
    """Write a trace record to logs/traces.jsonl and return the record."""
    cost = estimate_cost(provider, input_tokens, output_tokens)
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agent_name": agent_name,
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost,
        "latency_ms": latency_ms,
        "doc_id": doc_id,
        "success": success,
        "error": error,
    }
    TRACES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_all_traces() -> list[dict]:
    """Read all trace records from traces.jsonl."""
    if not TRACES_PATH.exists():
        return []
    records: list[dict] = []
    with open(TRACES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
