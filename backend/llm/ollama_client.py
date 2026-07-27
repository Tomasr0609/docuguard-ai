"""Ollama client — local LLM inference via the official ollama Python library.

Requires:
    - Ollama installed: https://ollama.com/
    - Model pulled: ollama pull llama3.2:3b  (o el modelo configurado en OLLAMA_MODEL)

Matcha exactamente la interfaz de anthropic_client.py:
    async def ollama_call(prompt, system, model, max_tokens, temperature) -> (text, input_tokens, output_tokens)
"""
from typing import Optional

from ollama import AsyncClient

from backend.config import settings


async def ollama_call(
    prompt: str,
    system: Optional[str] = None,
    model: str = "llama3.2:3b",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> tuple[str, int, int]:
    """Call a local Ollama model and return (response_text, input_tokens, output_tokens).

    Token counts come from the model's actual prompt_eval_count / eval_count.
    """
    client = AsyncClient(host=settings.ollama_base_url)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat(
        model=model,
        messages=messages,
        options={
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    )

    text = response["message"]["content"].strip()
    input_tokens = int(response.get("prompt_eval_count", 0) or 0)
    output_tokens = int(response.get("eval_count", 0) or 0)

    return text, input_tokens, output_tokens
