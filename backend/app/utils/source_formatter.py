def format_sources(docs, max_length: int = 300):
    formatted = []

    for doc in docs:
        content = doc.get("content", "")

        excerpt = (
            content
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("  ", " ")
        )[:max_length]

        formatted.append({
            "source_id": doc.get("source_id"),
            "document_name": doc.get("document_name"),
            "chunk_id": doc.get("chunk_id"),
            "score": round(doc.get("score", 0), 3),
            "excerpt": excerpt
        })

    return formatted