"""Gemini access for the rest of the app. Import this, not google.genai."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment.")
    return key


_CLIENT: genai.Client | None = None


def _client() -> genai.Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = genai.Client(api_key=_api_key())
    return _CLIENT


def complete(
    user: str,
    *,
    system: str | None = None,
    model: str | None = None,
) -> str:
    """Plain-text completion. Used later by the itinerary reporter."""
    response = _client().models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("LLM returned empty text")
    return text


def complete_json(
    user: str,
    *,
    system: str | None = None,
    schema: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """JSON completion. Used by the extractor to build a TripSpec."""
    config_kwargs: dict[str, Any] = {
        "system_instruction": system,
        "response_mime_type": "application/json",
    }
    if schema is not None:
        config_kwargs["response_json_schema"] = schema
    response = _client().models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    raw = (response.text or "").strip()
    if not raw:
        raise RuntimeError("LLM returned empty JSON")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("LLM JSON must be an object")
    return data


def user_text(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def _jsonable(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"result": json.loads(json.dumps(value, default=str))}
    return json.loads(json.dumps(value, default=str))


def tool_result_content(results: list[tuple[str, Any]]) -> types.Content:
    parts = [
        types.Part.from_function_response(name=name, response=_jsonable(payload))
        for name, payload in results
    ]
    return types.Content(role="user", parts=parts)


def text_from_content(content: types.Content) -> str:
    chunks = [part.text for part in (content.parts or []) if getattr(part, "text", None)]
    text = "\n".join(chunk for chunk in chunks if chunk).strip()
    return text or "(no text from model)"


def generate_with_tools(
    history: list[types.Content],
    *,
    system: str | None = None,
    declarations: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> types.Content:
    """One model turn with Gemini function calling."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=declarations or [])],
    )
    response = _client().models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=history,
        config=config,
    )
    if not response.candidates:
        raise RuntimeError("LLM returned no candidates")
    content = response.candidates[0].content
    if content is None:
        raise RuntimeError("LLM returned empty content")
    return content
