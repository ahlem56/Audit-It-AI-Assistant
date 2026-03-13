from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)

def split_documents(docs):
    chunks = splitter.split_documents(docs)
    return chunks