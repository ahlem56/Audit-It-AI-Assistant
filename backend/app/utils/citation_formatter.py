from __future__ import annotations


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
