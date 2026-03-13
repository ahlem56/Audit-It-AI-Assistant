def build_cited_context(docs):
    """
    Transforme les documents récupérés en contexte numéroté pour le LLM.
    """
    context_parts = []
    cited_sources = []

    for i, doc in enumerate(docs, start=1):
        source_id = f"Source {i}"

        content = doc.get("content", "")
        document_name = doc.get("document_name", "unknown")
        chunk_id = doc.get("chunk_id", None)
        score = doc.get("score", 0)

        context_parts.append(
            f"""[{source_id}]
document_name: {document_name}
chunk_id: {chunk_id}
content: {content}
"""
        )

        cited_sources.append({
            "source_id": source_id,
            "document_name": document_name,
            "chunk_id": chunk_id,
            "score": score,
            "content": content
        })

    context = "\n\n".join(context_parts)

    return context, cited_sources