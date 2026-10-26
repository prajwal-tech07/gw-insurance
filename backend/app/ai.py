"""Thin wrapper around the Claude API. Every caller has a non-AI fallback."""

import logging
from typing import Any

from app.config import claude_model, llm_enabled

log = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-fable-5"}


def get_client(client: Any = None) -> Any:
    """The given client (tests pass a fake), a real one if a key is configured, else None."""
    if client is not None:
        return client
    if not llm_enabled():
        return None
    import anthropic

    return anthropic.Anthropic()


def create_message(client: Any, **request: Any) -> Any:
    request.setdefault("model", claude_model())
    if request["model"] in FALLBACK_MODELS:
        return client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
    return client.messages.create(**request)


def first_text(response: Any) -> str | None:
    return next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)


def complete_text(system: str, prompt: str, client: Any = None) -> tuple[str | None, str | None]:
    """Plain-text completion. Returns (text, error); never raises."""
    try:
        client = get_client(client)
        if client is None:
            return None, "no API key configured"
        response = create_message(client, max_tokens=16000, system=system,
                                  messages=[{"role": "user", "content": prompt}],
                                  output_config={"effort": "low"})
        if response.stop_reason in ("refusal", "max_tokens"):
            return None, f"stopped: {response.stop_reason}"
        text = first_text(response)
        return (text.strip(), None) if text else (None, "empty answer")
    except Exception as exc:
        log.warning("AI call failed: %s", exc)
        return None, type(exc).__name__
