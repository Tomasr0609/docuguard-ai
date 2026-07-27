"""Generate a summary report from logs/traces.jsonl.

Usage:
    python scripts/traces_report.py              # full report
    python scripts/traces_report.py --json        # output as JSON
"""
import json
import sys
import os
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.observability.tracing import read_all_traces


def build_report(records: list[dict]) -> dict[str, Any]:
    if not records:
        return {"status": "empty", "message": "No traces found in logs/traces.jsonl"}

    total_cost = sum(r.get("estimated_cost_usd", 0) for r in records)
    total_input_tokens = sum(r.get("input_tokens", 0) for r in records)
    total_output_tokens = sum(r.get("output_tokens", 0) for r in records)

    success_count = sum(1 for r in records if r.get("success", False))
    fail_count = len(records) - success_count

    # Per-agent stats
    agent_stats: dict[str, dict] = {}
    for r in records:
        agent = r.get("agent_name", "unknown")
        lat = r.get("latency_ms", 0)
        cost = r.get("estimated_cost_usd", 0)
        if agent not in agent_stats:
            agent_stats[agent] = {"calls": 0, "total_latency": 0, "total_cost": 0, "failures": 0}
        agent_stats[agent]["calls"] += 1
        agent_stats[agent]["total_latency"] += lat
        agent_stats[agent]["total_cost"] += cost
        if not r.get("success", True):
            agent_stats[agent]["failures"] += 1

    for stats in agent_stats.values():
        stats["avg_latency_ms"] = round(stats["total_latency"] / stats["calls"], 1) if stats["calls"] else 0
        stats["avg_cost_per_call"] = round(stats["total_cost"] / stats["calls"], 6) if stats["calls"] else 0

    # Per-doc stats
    doc_costs = defaultdict(float)
    doc_latencies = defaultdict(list)
    for r in records:
        doc_id = r.get("doc_id") or "unknown"
        doc_costs[doc_id] += r.get("estimated_cost_usd", 0)
        doc_latencies[doc_id].append(r.get("latency_ms", 0))

    avg_latency_all = sum(r.get("latency_ms", 0) for r in records) / len(records) if records else 0

    provider_counts = Counter(r.get("provider", "unknown") for r in records)

    return {
        "status": "ok",
        "total_calls": len(records),
        "successful_calls": success_count,
        "failed_calls": fail_count,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": round(total_cost, 4),
        "avg_latency_ms": round(avg_latency_all, 1),
        "provider_breakdown": dict(provider_counts),
        "agents": agent_stats,
    }


def print_report(report: dict) -> None:
    if report["status"] == "empty":
        print(report["message"])
        return

    print("=" * 60)
    print("  DOCUGUARD AI LITE — TRACES REPORT")
    print("=" * 60)
    print(f"  Total LLM calls:    {report['total_calls']}")
    print(f"  Successful:          {report['successful_calls']}")
    print(f"  Failed:              {report['failed_calls']}")
    print(f"  Total input tokens:  {report['total_input_tokens']}")
    print(f"  Total output tokens: {report['total_output_tokens']}")
    print(f"  Total cost (USD):    ${report['total_cost_usd']:.4f}")
    print(f"  Avg latency:         {report['avg_latency_ms']} ms")
    print(f"  Providers:           {report['provider_breakdown']}")
    print()
    print("  Per-agent breakdown:")
    print(f"  {'Agent':<20} {'Calls':>6} {'Avg Lat':>10} {'Avg $':>10} {'Fail':>5}")
    print("  " + "-" * 51)
    for agent, stats in sorted(report["agents"].items()):
        print(f"  {agent:<20} {stats['calls']:>6} {stats['avg_latency_ms']:>8.1f}ms {stats['avg_cost_per_call']:>8.6f} {stats['failures']:>5}")
    print("=" * 60)


def main() -> None:
    records = read_all_traces()
    report = build_report(records)

    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
