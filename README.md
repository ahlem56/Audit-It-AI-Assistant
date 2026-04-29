# Audit IT AI Assistant

Audit IT AI Assistant is a web application designed to support ITGC audit missions from mission setup to final report export. It helps auditors import audit workbooks, review observations, calculate priorities, generate recommendations, interact with an AI assistant, build structured reports, export deliverables, and collect auditor feedback.

## Main Features

- Secure workspace with optional Microsoft Entra authentication.
- Mission creation and mission selection.
- Excel import for ITGC audit observations.
- Observation register with search, filters, validation status, manual edits, and priority recalculation.
- AI-assisted risk, impact, priority, and recommendation generation.
- ITGC control catalog used as a business reference and fallback layer.
- Mission chat assistant aware of the selected mission context.
- Report review studio with quality gate checks.
- Export to PowerPoint, PDF, and Word.
- Optional report email sending.
- Auditor feedback loop with ratings, categories, status tracking, and improvement history.

## Project Structure

```text
backend/
  app/
    agents/       AI agents for audit reasoning, priority logic, QA, and report generation
    api/          FastAPI routes
    config/       Environment-based settings
    db/           Database models and sessions
    domain/       ITGC control catalog
    models/       Pydantic models
    services/     Business services, exports, storage, retrieval, auth, and quality gate
    utils/        Parsers and formatting utilities
  scripts/        Utility scripts for templates, migration, and validation

frontend/
  src/
    components/   Shared UI components
    context/      Auth, language, and mission contexts
    pages/        Main application pages
    services/     API client
    types/        Frontend types
```

## Tech Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- Backend: FastAPI, Python
- AI and retrieval: LangChain, Azure OpenAI, Azure AI Search
- Storage integrations: Azure Blob Storage, optional Azure SQL
- Documents: PowerPoint, PDF, Word, Excel parsing

## Setup

### 1. Backend

Create and activate a Python virtual environment:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create the real environment file from the template:

```powershell
Copy-Item .env.example .env
```

Then fill `backend/.env` with your local or cloud configuration.

Run the backend:

```powershell
uvicorn app.main:app --reload
```

The backend runs by default on:

```text
http://127.0.0.1:8000
```

### 2. Frontend

Install dependencies and run the Vite dev server:

```powershell
cd frontend
npm install
npm run dev
```

The frontend usually runs on:

```text
http://localhost:5173
```

## Environment Files

`backend/.env.example` is committed as a safe template. It documents the variables needed by the backend.

`backend/.env` is local only and must not be committed because it can contain secrets such as API keys, database credentials, and authentication settings.

## Data Folder Policy

The project ignores local runtime data such as:

- local SQLite auth database;
- generated mission data;
- uploaded profile images;
- generated previews;
- local report caches;
- Python caches and server logs.

Some template files may still be required for export features, especially:

- `backend/app/data/Template PWC Universal v2.pptx`
- `backend/app/data/rapport_template_dynamic.docx`

Keep required templates available locally or provide them through a controlled setup process.

## Typical Workflow

1. Sign in to the application.
2. Create or select an audit mission.
3. Upload the ITGC Excel workbook.
4. Review observations and edit them if needed.
5. Recalculate priorities and recommendations.
6. Ask the mission chat assistant for explanations or recommendations.
7. Open the report review studio.
8. Check the quality gate.
9. Export the report as PPTX, PDF, or Word.
10. Capture auditor feedback for continuous improvement.

## Notes for GitHub

Before pushing, make sure generated files are not tracked:

```powershell
git status --short
```

If runtime files were already committed, remove them from Git tracking while keeping them locally:

```powershell
git rm -r --cached backend/app/data/missions
git rm --cached backend/app/data/auth.sqlite3
git rm --cached backend/app/data/latest_audit_input.json
git add .gitignore
git commit -m "chore: remove generated backend data from repository"
git push
```

If secrets were ever committed, rotate them and clean the Git history.
