# PwC Audit ITGC Assistant

Modern React + TypeScript frontend for a professional ITGC audit assistant.

## Features
- Persistent left sidebar with mission navigation
- Workspace home with mission metadata and upload status
- Editable observations table powered by TanStack Table
- AI assistant chat interface with mission context
- Report preview and PPTX export flow
- Dashboard with charts using Recharts
- Tailwind CSS styling and enterprise-grade design
- Mock data for `Paref FY25` ready to explore

## Setup
1. Install dependencies:
   ```bash
   npm install
   ```
2. Start development server:
   ```bash
   npm run dev
   ```
3. Open the local Vite URL shown in your terminal.

## Backend integration
- `POST /upload`
- `POST /assistant`
- `GET /assistant/export`
- `POST /chat`

If the backend is unavailable, mock data is used automatically.
