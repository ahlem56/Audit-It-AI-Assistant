from __future__ import annotations


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
