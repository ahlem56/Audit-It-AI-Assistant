from __future__ import annotations

import re


def normalize_citations(text: str) -> str:
    """
    Normalize citation formats like:
    [Source 1, Source 2, Source 3]
    [Source 1], [Source 2]
    [Source 1]; [Source 2]

    into:
    [Source 1][Source 2][Source 3]
    """
    pattern = r"\[(Source\s*\d+(?:\s*[,;]\s*Source\s*\d+)+)\]"
    matches = re.findall(pattern, text)

    for match in matches:
        sources = re.findall(r"Source\s*\d+", match)
        normalized = "".join([f"[{source.strip()}]" for source in sources])
        text = text.replace(f"[{match}]", normalized)

    return re.sub(
        r"\[Source\s*(\d+)\]\s*[,;]\s*\[Source\s*(\d+)\]",
        r"[Source \1][Source \2]",
        text,
    )


def build_cited_context(docs):
    """Transform retrieved documents into a numbered context for the LLM."""
    context_parts = []
    cited_sources = []

    for index, doc in enumerate(docs, start=1):
        source_id = f"Source {index}"
        content = doc.get("content", "")
        document_name = doc.get("document_name", "unknown")
        chunk_id = doc.get("chunk_id")
        score = doc.get("score", 0)

        context_parts.append(
            f"""[{source_id}]
document_name: {document_name}
chunk_id: {chunk_id}
content: {content}
"""
        )

        cited_sources.append(
            {
                "source_id": source_id,
                "document_name": document_name,
                "chunk_id": chunk_id,
                "score": score,
                "content": content,
            }
        )

    return "\n\n".join(context_parts), cited_sources


def format_sources(docs, max_length: int = 300):
    formatted = []

    for doc in docs:
        content = doc.get("content", "")
        excerpt = " ".join(content.replace("\r", " ").replace("\n", " ").split())[:max_length]
        score = doc.get("score")

        formatted.append(
            {
                "source_id": doc.get("source_id"),
                "document_name": doc.get("document_name"),
                "chunk_id": doc.get("chunk_id"),
                "score": round(score, 3) if isinstance(score, (int, float)) else None,
                "excerpt": excerpt,
            }
        )

    return formatted
