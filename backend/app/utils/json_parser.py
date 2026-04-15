from __future__ import annotations

import json
import re
from json import JSONDecoder


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _candidate_payloads(text: str) -> list[str]:
    value = (text or "").strip()
    candidates: list[str] = []

    if value:
        candidates.append(value)

    for match in _CODE_FENCE_RE.finditer(value):
        inner = (match.group(1) or "").strip()
        if inner:
            candidates.append(inner)

    return candidates


def _raw_decode_first_json(text: str):
    decoder = JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[idx:])
            return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError("No valid JSON object or array found in LLM response")


def extract_json_from_response(text: str):
    """
    Extract the first valid JSON payload from an LLM response.

    This is intentionally tolerant because some model responses include:
    - markdown code fences
    - explanatory text before/after the JSON
    - multiple blocks where the first valid JSON block is the useful one
    """
    last_error: Exception | None = None
    for candidate in _candidate_payloads(text):
        try:
            return _raw_decode_first_json(candidate)
        except Exception as exc:  # keep trying other candidates
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("No JSON payload found in LLM response")
