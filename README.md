# IT Audit AI Assistant

> Automated generation of IT Audit Reports, Risk Control Matrices (RCM), and Audit Observations using a multi-agent RAG architecture.

Developed as a final-year engineering project (PFE) at ESPRIT, in collaboration with **Conseil Audit Formation – PwC Tunisia**, Assurance & Risk Assurance Services (RAS) department.

---

## Overview

IT audit missions require auditors to analyze large volumes of technical documents — security policies, IT procedures, system architecture documents, internal control reports, and event logs — before producing structured deliverables such as Risk Control Matrices (RCM), audit observations, and audit reports.

This project addresses that challenge by providing an intelligent assistant that automates document analysis and deliverable generation, reducing repetitive manual work and improving consistency across audit engagements.

---

## Features

- Upload and analyze IT audit documents (PDF, DOCX, etc.)
- Automatic extraction of risks, controls, and weaknesses from unstructured text
- Automatic generation of IT-oriented Risk Control Matrices (RCM)
- Automatic generation of structured audit observations (condition, cause, impact, recommendation)
- Automatic generation of complete IT audit reports
- Conversational interface to query and explore uploaded documents
- Download of all generated deliverables

---

## Architecture

The system is built around three core architectural principles:

### RAG (Retrieval Augmented Generation)

Documents are chunked, embedded, and indexed into a vector store (Azure AI Search). When a user submits a query or requests a deliverable, the system retrieves the most relevant document passages before passing them to the language model, grounding the generated output in the actual content of the uploaded files.

### Multi-Agent System

The system orchestrates several specialized agents, each responsible for a distinct task:

| Agent | Responsibility |
|---|---|
| Orchestrator Agent | Interprets user requests and coordinates all other agents |
| Document Analysis Agent | Extracts risks, controls, and relevant information from uploaded documents |
| RCM Generation Agent | Builds Risk Control Matrices from extracted information |
| Observation Generation Agent | Produces structured audit observations for identified weaknesses |
| Audit Report Generation Agent | Generates a complete, structured IT audit report |
| Question Answering Agent | Answers user questions in a conversational interface using the vector store |

### System Layers

```
[ React Frontend ]
        |
[ FastAPI Backend ]
        |
   ___________________________________________
  |                   |                       |
[ LangChain        [ Azure OpenAI          [ Azure AI Search ]
  Multi-Agent        GPT-4o + text-          (Vector Store)
  Orchestration ]    embedding-3-large ]
                                          [ Azure Blob Storage ]
                                            (Document Storage)
```

---

## Tech Stack

### Frontend
- React

### Backend
- Python
- FastAPI

### AI Layer
- LangChain (agent orchestration and RAG pipeline)
- Azure OpenAI — `GPT-4o` for text generation, `text-embedding-3-large` for embeddings

### Cloud Infrastructure
- Azure Blob Storage — document storage
- Azure AI Search — vector indexing and semantic search

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- An Azure subscription with the following services configured:
  - Azure OpenAI (with GPT-4o and text-embedding-3-large deployments)
  - Azure AI Search
  - Azure Blob Storage

### Installation

**Clone the repository**

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

**Backend setup**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the environment file and fill in your Azure credentials:

```bash
cp .env.example .env
```

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT_GPT4O=
AZURE_OPENAI_DEPLOYMENT_EMBEDDING=
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER_NAME=
```

Start the backend:

```bash
uvicorn main:app --reload
```

**Frontend setup**

```bash
cd frontend
npm install
npm run dev
```

---

## Project Structure

```
.
├── backend/
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── document_analysis.py
│   │   ├── rcm_generation.py
│   │   ├── observation_generation.py
│   │   ├── report_generation.py
│   │   └── question_answering.py
│   ├── services/
│   │   ├── vector_store.py
│   │   └── document_loader.py
│   ├── routers/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   └── pages/
│   └── package.json
└── README.md
```

---

## Functional Requirements

- Upload IT audit documents through the web interface
- Automatic analysis and information extraction from uploaded documents
- Conversational Q&A grounded in document content
- Automatic RCM generation (risk, associated control, test procedure)
- Automatic audit observation generation (condition, cause, impact, recommendation)
- Automatic structured IT audit report generation
- Download of all generated outputs

## Non-Functional Requirements

- **Performance**: Responses delivered within a reasonable time frame
- **Scalability**: System handles growing document volumes and concurrent users
- **Security**: Confidentiality of sensitive audit documents ensured via Azure security controls
- **Reliability**: Consistent, coherent outputs that auditors can use as a working base
- **Usability**: Simple, intuitive interface requiring no technical expertise

---

## Project Timeline

| Phase | Description |
|---|---|
| Analysis | Understanding IT audit processes, technology study, requirement definition |
| Design | System architecture, component identification, module interaction specification |
| Development | Frontend, backend, AI integration, vector store setup |
| Testing | Functional and integration testing of all modules |
| Deployment | Prototype finalization and demonstration |

Stage period: February 2026 – July 2026

---

## Academic Context

- Institution: ESPRIT — Ecole Superieure Privee d'Ingenierie et de Technologie
- Student: Ahlem Bouchahoua
- Academic supervisor: Khadija Raissi
- Company supervisor: Emna Zanni (PwC)
- Host organization: Conseil Audit Formation, member of the PwC network — Assurance / RAS department

---

## License

This project was developed as part of a final-year internship (PFE). All rights reserved.
