from __future__ import annotations


_CURRENT_QUESTION_MARKER = "\n\nCurrent question:\n"


def extract_current_question(value: str) -> str:
    text = (value or "").strip()
    if _CURRENT_QUESTION_MARKER in text:
        return text.rsplit(_CURRENT_QUESTION_MARKER, 1)[-1].strip()
    return text
