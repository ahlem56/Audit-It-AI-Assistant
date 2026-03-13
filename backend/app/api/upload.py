from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import tempfile

from app.services.blob_service import upload_file
from app.utils.document_parser import load_document
from app.services.rag_service import split_documents
from app.services.indexing_service import prepare_documents_for_index
from app.services.search_service import upload_documents_to_index

router = APIRouter()

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        # 1. Lire le contenu du fichier
        content = await file.read()

        # 2. Upload dans Azure Blob Storage
        upload_file(file.filename, content)

        # 3. Sauvegarde temporaire locale pour parsing
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        try:
            # 4. Parser le document
            docs = load_document(temp_file_path)

            # 5. Découper en chunks
            chunks = split_documents(docs)

            # 6. Préparer les documents pour Azure Search
            indexed_docs = prepare_documents_for_index(chunks, file.filename)

            # 7. Push vers Azure AI Search
            upload_result = upload_documents_to_index(indexed_docs)

        finally:
            # 8. Supprimer le fichier temporaire
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        return {
            "message": "Document uploaded and indexed successfully",
            "filename": file.filename,
            "chunks_indexed": len(indexed_docs)
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload/indexing failed: {str(e)}")