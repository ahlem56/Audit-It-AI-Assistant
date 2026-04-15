from __future__ import annotations

from app.services.embedding_service import create_embedding


def sanitize_filename(filename: str) -> str:
    return (
        filename.replace(" ", "_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def prepare_documents_for_index(chunks, filename: str, mission_id: str):
    prepared_docs = []
    safe_name = sanitize_filename(filename)

    for index, chunk in enumerate(chunks):
        content = chunk.page_content.strip()
        if not content:
            continue

        prepared_docs.append(
            {
                "id": f"{safe_name}_{index}",
                "content": content,
                "document_name": filename,
                "chunk_id": index,
                "mission_id": mission_id,
                "content_vector": create_embedding(content),
            }
        )

    return prepared_docs
