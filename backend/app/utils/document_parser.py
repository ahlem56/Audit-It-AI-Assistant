from __future__ import annotations

from langchain_community.document_loaders import PyPDFLoader, TextLoader

from app.utils.excel_parser import load_excel_document

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".xlsx", ".xlsm"}


def load_document(file_path: str):
    lower_path = file_path.lower()

    if lower_path.endswith(".pdf"):
        return PyPDFLoader(file_path).load()
    if lower_path.endswith(".txt"):
        return TextLoader(file_path, encoding="utf-8").load()
    if lower_path.endswith(".xlsx") or lower_path.endswith(".xlsm"):
        return load_excel_document(file_path)

    raise ValueError(
        f"Unsupported file type: {file_path}. Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )
