from app.services.embedding_service import create_embedding

def sanitize_filename(filename: str) -> str:
    return (
        filename.replace(" ", "_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )

def prepare_documents_for_index(chunks, filename: str):
    prepared_docs = []
    safe_name = sanitize_filename(filename)

    for i, chunk in enumerate(chunks):
        content = chunk.page_content.strip()

        if not content:
            continue

        embedding = create_embedding(content)

        prepared_docs.append({
            "id": f"{safe_name}_{i}",
            "content": content,
            "document_name": filename,
            "chunk_id": i,
            "content_vector": embedding
        })

    return prepared_docs