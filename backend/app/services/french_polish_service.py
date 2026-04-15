from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.agents.french_polisher_agent import polish_french_texts
from app.utils.french_normalizer import normalize_french

ENABLE_FRENCH_POLISH = os.getenv("ENABLE_FRENCH_POLISH", "false").lower() == "true"


@dataclass(frozen=True)
class _TextItem:
    path: str
    text: str


def _collect_strings(node: Any, path: str, out: list[_TextItem]) -> None:
    if isinstance(node, str):
        if node.strip():
            out.append(_TextItem(path=path, text=node))
        return
    if isinstance(node, list):
        for i, item in enumerate(node):
            _collect_strings(item, f"{path}[{i}]", out)
        return
    if isinstance(node, dict):
        for key, value in node.items():
            # Don't polish keys; only values.
            _collect_strings(value, f"{path}.{key}" if path else str(key), out)


def _set_by_path(root: Any, path: str, new_text: str) -> None:
    # Path grammar: "a.b[0].c"
    current = root
    tokens: list[str] = []
    buf = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if buf:
                tokens.append(buf)
                buf = ""
            i += 1
            continue
        if ch == "[":
            if buf:
                tokens.append(buf)
                buf = ""
            j = path.find("]", i)
            idx = int(path[i + 1 : j])
            tokens.append(f"[{idx}]")
            i = j + 1
            continue
        buf += ch
        i += 1
    if buf:
        tokens.append(buf)

    for tok in tokens[:-1]:
        if tok.startswith("[") and tok.endswith("]"):
            current = current[int(tok[1:-1])]
        else:
            current = current[tok]

    last = tokens[-1]
    if last.startswith("[") and last.endswith("]"):
        current[int(last[1:-1])] = new_text
    else:
        current[last] = new_text


def polish_report_payload(payload: dict[str, Any], *, max_items_per_call: int = 60) -> dict[str, Any]:
    """
    Applies a sentence-level French polish pass on ALL string fields.
    Falls back to deterministic normalization if LLM polishing fails.
    """
    if not ENABLE_FRENCH_POLISH:
        return payload

    items: list[_TextItem] = []
    _collect_strings(payload, "", items)

    if not items:
        return payload

    updated = payload
    # Chunk to keep prompts bounded.
    for start in range(0, len(items), max_items_per_call):
        chunk = items[start : start + max_items_per_call]
        req = [{"path": item.path, "text": item.text} for item in chunk]
        try:
            resp = polish_french_texts(req)
            for row in resp:
                _set_by_path(updated, row["path"], row["text"])
        except Exception:
            # Fallback: deterministic normalization only.
            for item in chunk:
                _set_by_path(updated, item.path, normalize_french(item.text))

    return updated
