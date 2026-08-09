"""Claude-powered analysis of a pitch deck transcript.

The JSON schema, the field instructions, and the analysis rules are all derived
from ``template.py`` — this module contains no field list of its own.
"""

from __future__ import annotations

import json
import os

import anthropic

import template
from extractor import format_pages

DEFAULT_MODEL = "claude-opus-5"
MAX_TOKENS = 16_000
MAX_TRANSCRIPT_CHARS = 400_000

_RETRY_INSTRUCTION = (
    "Your previous response was not valid JSON. Return valid JSON only — a single object "
    "with the required keys, no markdown fences, no commentary before or after."
)


class AnalysisError(RuntimeError):
    """Raised when the Claude API call fails or returns unusable output."""


def analyze_deck(
    pages: list[str],
    *,
    source_name: str = "deck",
    model: str | None = None,
    api_key: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> dict[str, str]:
    """Analyze a deck transcript and return one string per template field.

    Args:
        pages: Page/slide text in document order.
        source_name: Source filename, included in the prompt for context.
        model: Claude model ID. Defaults to ``$ANTHROPIC_MODEL`` or ``claude-opus-5``.
        api_key: Console API key. Defaults to ``$ANTHROPIC_API_KEY``.
        client: Pre-built Anthropic client, overriding ``api_key``.

    Returns:
        A dict keyed by ``template.field_keys()``, every value a non-empty string.
        Missing values are filled with the template's fallback text.

    Raises:
        AnalysisError: The API key is missing, the request fails, the model
            refuses, or the response is not parseable JSON after one retry.
    """
    transcript = format_pages(pages)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = (
            transcript[:MAX_TRANSCRIPT_CHARS]
            + "\n\n[Transcript truncated — deck exceeded the analysis size limit.]"
        )

    client = client or build_client(api_key)
    model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    keys = template.field_keys()

    messages: list[dict] = [{"role": "user", "content": _build_prompt(transcript, source_name)}]
    raw = _request(client, model, messages, keys)
    parsed = _loads(raw)
    if parsed is None:
        messages.append({"role": "user", "content": _RETRY_INSTRUCTION})
        raw = _request(client, model, messages, keys)
        parsed = _loads(raw)
    if parsed is None:
        raise AnalysisError(
            "Claude did not return valid JSON after a retry. "
            f"First 300 characters of the response: {raw[:300]!r}"
        )
    return _normalize(parsed, keys)


def build_client(api_key: str | None = None) -> anthropic.Anthropic:
    """Build an Anthropic client from an explicit key or the environment.

    Args:
        api_key: Console API key. Falls back to ``$ANTHROPIC_API_KEY``.

    Raises:
        AnalysisError: No key is available, or the client cannot be constructed.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AnalysisError(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY in your .env file, your "
            "shell, or your Railway service variables."
        )
    try:
        return anthropic.Anthropic(api_key=key)
    except Exception as exc:
        raise AnalysisError(f"Could not create an Anthropic client: {exc}") from exc


def _build_prompt(transcript: str, source_name: str) -> str:
    """Assemble the user turn: per-field instructions plus the deck transcript."""
    guidance = "\n".join(
        f"- {key}: {template.FIELD_GUIDANCE[key]}" for key in template.field_keys()
    )
    return (
        f"Analyze the pitch deck below (source file: {source_name}) and return one JSON "
        "object with these fields:\n\n"
        f"{guidance}\n\n"
        "=== BEGIN DECK TRANSCRIPT ===\n"
        f"{transcript}\n"
        "=== END DECK TRANSCRIPT ==="
    )


def _system_prompt() -> str:
    """Build the system prompt from the template's analysis rules."""
    rules = "\n".join(f"- {rule}" for rule in template.ANALYSIS_RULES)
    return (
        f"You are a venture analyst at {template.ORGANIZATION}. You read investor pitch decks "
        "and produce structured summaries for an investment audience.\n\nRules:\n" + rules
    )


def _schema(keys: tuple[str, ...]) -> dict:
    """Build the JSON schema Claude's response is constrained to."""
    return {
        "type": "object",
        "properties": {key: {"type": "string"} for key in keys},
        "required": list(keys),
        "additionalProperties": False,
    }


def _request(
    client: anthropic.Anthropic, model: str, messages: list[dict], keys: tuple[str, ...]
) -> str:
    """Send one Messages API request and return the concatenated text response."""
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=_system_prompt(),
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": _schema(keys)}},
        )
    except anthropic.AuthenticationError as exc:
        raise AnalysisError(
            "Anthropic rejected the API key. Check ANTHROPIC_API_KEY in your Claude Console."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise AnalysisError("Anthropic rate limit reached. Wait a moment and try again.") from exc
    except anthropic.APIStatusError as exc:
        raise AnalysisError(f"Claude API error ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise AnalysisError(f"Could not reach the Claude API: {exc}") from exc

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "explanation", None) or "no explanation given"
        raise AnalysisError(f"Claude declined to analyze this document: {detail}")
    if response.stop_reason == "max_tokens":
        raise AnalysisError(
            "Claude hit the output token limit before finishing. Try a shorter document."
        )

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise AnalysisError("Claude returned an empty response.")
    return text


def _loads(raw: str) -> dict | None:
    """Parse a JSON object, returning None if the text is not a JSON object."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize(parsed: dict, keys: tuple[str, ...]) -> dict[str, str]:
    """Coerce every template field to a non-empty string, filling gaps with the fallback."""
    result: dict[str, str] = {}
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
        elif value is None or isinstance(value, str):
            result[key] = template.FALLBACK_VALUE
        else:
            result[key] = str(value)
    return result
