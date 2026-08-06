import asyncio
import logging
import time
from collections import deque
from typing import Optional

from google import genai
from google.genai import types

from backend.config import settings

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None

# --- Rate limiter ---------------------------------------------------------
# Free tier is 15 RPM; we cap at 12 to leave safety margin.
_MAX_CALLS_PER_WINDOW = 12
_WINDOW_SECONDS = 60.0

_call_timestamps: deque[float] = deque()
_rate_limit_lock = asyncio.Lock()


async def _wait_for_rate_limit() -> None:
    """Block until it's safe to make another call without exceeding the RPM quota."""
    async with _rate_limit_lock:
        now = time.monotonic()

        # Drop timestamps older than the window
        while _call_timestamps and now - _call_timestamps[0] > _WINDOW_SECONDS:
            _call_timestamps.popleft()

        if len(_call_timestamps) >= _MAX_CALLS_PER_WINDOW:
            wait_time = _WINDOW_SECONDS - (now - _call_timestamps[0]) + 0.5
            if wait_time > 0:
                logger.info(
                    "gemini_client: rate limit guard, esperando %.1fs antes de la siguiente llamada",
                    wait_time,
                )
                await asyncio.sleep(wait_time)
            # Re-clean after waiting
            now = time.monotonic()
            while _call_timestamps and now - _call_timestamps[0] > _WINDOW_SECONDS:
                _call_timestamps.popleft()

        _call_timestamps.append(time.monotonic())
# ---------------------------------------------------------------------------

# Explicit request timeout (ms) so a stuck call fails fast and visibly
# instead of hanging silently for minutes.
_REQUEST_TIMEOUT_MS = 30_000


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY no configurada. "
                "Creala en https://aistudio.google.com/apikey "
                "y agregala al archivo .env"
            )
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
    return _client


async def gemini_call(
    prompt: str,
    system: Optional[str] = None,
    model: str = "gemini-flash-lite-latest",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> tuple[str, int, int]:
    """Call Gemini and return (response_text, input_tokens, output_tokens).

    Token counts come from response.usage_metadata when available.
    Cost is always 0.0 for the free tier.
    """
    await _wait_for_rate_limit()

    client = get_client()

    content_config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        temperature=temperature,
        # Disabled explicitly: this pipeline never uses function/tool calling,
        # and leaving AFC enabled can cause silent multi-minute stalls.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=content_config,
        )
    except Exception as e:
        logger.error("gemini_client: generate_content failed or timed out: %s", e)
        raise

    text = response.text.strip() if response.text else ""

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0

    return text, input_tokens, output_tokens