"""LLM Router — routes tasks to the appropriate provider.

Architecture note:
    The router dispatches to Anthropic or Ollama based on the LLM_PROVIDER
    environment variable (default: ollama). No agent code needs to change
    when switching providers — the routing is transparent.

    In production, this would also dispatch based on task_type and
    confidence_hint (e.g., Ollama for cheap classification, Claude for
    high-stakes extraction). The contract is designed so that adding
    a new provider requires only:
    1. Adding the provider to the route() mapping
    2. Adding the call in call_llm()
"""
import time
import logging
from typing import Optional

from backend.config import settings
from backend.llm.anthropic_client import anthropic_call
from backend.llm.ollama_client import ollama_call
from backend.observability.tracing import log_llm_call

logger = logging.getLogger(__name__)


def route(task_type: str, confidence_hint: float = 1.0) -> str:
    """Return the provider name for a given task type.

    Controlled by LLM_PROVIDER in .env (default: ollama).
    Set LLM_PROVIDER=anthropic to switch back to Claude without code changes.
    """
    return settings.llm_provider


async def call_llm(
    prompt: str,
    system: Optional[str] = None,
    provider: Optional[str] = None,
    task_type: str = "general",
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    doc_id: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> str:
    """Centralized LLM call: routes to provider, logs trace, returns text.

    Every agent must use this function instead of calling providers directly.
    """
    if provider is None:
        provider = route(task_type)

    start_time = time.time()
    success = True
    error_msg: Optional[str] = None
    text = ""
    input_tokens = 0
    output_tokens = 0
    resolved_model = model or "default"

    try:
        if provider == "anthropic":
            text, input_tokens, output_tokens = await anthropic_call(
                prompt=prompt,
                system=system,
                model=model or "claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=temperature,
            )
            resolved_model = model or "claude-sonnet-4-20250514"
        elif provider == "ollama":
            text, input_tokens, output_tokens = await ollama_call(
                prompt=prompt,
                system=system,
                model=model or settings.ollama_model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            resolved_model = model or settings.ollama_model
        else:
            raise ValueError(f"Unknown provider: {provider}")
    except Exception as e:
        success = False
        error_msg = str(e)
        logger.error(f"LLM call failed (provider={provider}, agent={agent_name}): {e}")
        raise

    finally:
        elapsed_ms = int((time.time() - start_time) * 1000)
        log_llm_call(
            agent_name=agent_name or task_type,
            task_type=task_type,
            provider=provider,
            model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
            doc_id=doc_id,
            success=success,
            error=error_msg,
        )

    return text
