"""Unit tests for the LLM router contract."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.llm.router import route
from backend.observability.tracing import estimate_cost


def test_route_defaults_to_ollama() -> None:
    """The router contract: by default returns 'ollama' (controlled by .env)."""
    for task_type in ("extraction", "verification", "classification", "writing"):
        assert route(task_type) == "ollama", f"route({task_type}) should return 'ollama'"


def test_route_with_confidence_hint() -> None:
    """confidence_hint should be accepted without error."""
    for confidence in (0.0, 0.5, 1.0):
        provider = route("classification", confidence_hint=confidence)
        assert provider == "ollama"


def test_route_unknown_task_type() -> None:
    """Even unknown task types must return a valid provider."""
    assert route("unknown_task") == "ollama"


def test_estimate_cost_anthropic() -> None:
    cost = estimate_cost("anthropic", input_tokens=1000, output_tokens=500)
    expected = 0.003 * 1 + 0.015 * 0.5  # 0.003 + 0.0075 = 0.0105
    assert abs(cost - expected) < 0.0001, f"Expected {expected}, got {cost}"


def test_estimate_cost_ollama_free() -> None:
    cost = estimate_cost("ollama", input_tokens=5000, output_tokens=2000)
    assert cost == 0.0, "Ollama should be free"


def test_estimate_cost_unknown_provider() -> None:
    """Unknown provider falls back to anthropic rates."""
    cost = estimate_cost("unknown", input_tokens=1000, output_tokens=500)
    expected = 0.0105
    assert abs(cost - expected) < 0.0001
