from typing import Optional

from anthropic import AsyncAnthropic

from backend.config import settings


_client: Optional[AsyncAnthropic] = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = settings.anthropic_api_key
        if not api_key or api_key == "sk-ant-...":
            raise ValueError(
                "ANTHROPIC_API_KEY no configurada. "
                "Copia .env.example a .env y completa la clave."
            )
        _client = AsyncAnthropic(api_key=api_key)
    return _client


async def anthropic_call(
    prompt: str,
    system: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> tuple[str, int, int]:
    """Call Anthropic Claude and return (response_text, input_tokens, output_tokens)."""
    client = get_client()

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system

    response = await client.messages.create(**kwargs)

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    usage = response.usage
    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0

    return text.strip(), input_tokens, output_tokens
