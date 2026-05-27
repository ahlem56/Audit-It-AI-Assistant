# Authentication Setup

This project now supports a single identity provider model:

- Microsoft Entra External ID manages sign-up, sign-in, password reset, and optional MFA
- FastAPI stores the local app user profile and the HTTP-only session
- React consumes the session through `/api/auth/me`

## What Entra should collect

Configure your Entra sign-up and sign-in user flow to collect:

- `Given name`
- `Surname`
- `Email address`
- `Password`

If you need more fields later, prefer Entra built-in attributes first. Keep app-specific role assignment in the backend.

## Required backend variables

Copy `backend/.env.example` to `backend/.env` and fill:

- `AUTH_ENABLED=true`
- `AUTH_FRONTEND_BASE_URL=http://localhost:4173`
- `AUTH_ENTRA_CLIENT_ID=...`
- `AUTH_ENTRA_CLIENT_SECRET=...`
- `AUTH_ENTRA_REDIRECT_URI=http://127.0.0.1:8000/auth/entra/callback`
- `AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI=http://localhost:4173/login`
- `AUTH_ENTRA_METADATA_URL=https://<tenant>.ciamlogin.com/<tenant>.onmicrosoft.com/v2.0/.well-known/openid-configuration?appid=<client-id>`

## Entra portal checklist

1. Create or use an `External tenant`
2. Register the web app in that tenant
3. Add redirect URI: `http://127.0.0.1:8000/auth/entra/callback`
4. Create a `Sign up and sign in` user flow
5. Enable `Email with password`
6. Add Microsoft identity provider if you want Microsoft sign-in on the same hosted page
7. Associate the app registration with the user flow
8. Copy the OpenID metadata URL for that app and user flow into `AUTH_ENTRA_METADATA_URL`

## Local app storage

The backend creates `backend/app/data/auth.sqlite3` with:

- `app_users`: local profile and role mapping
- `auth_sessions`: HTTP-only sessions
- `auth_states`: short-lived OIDC state and nonce records

## Dev mode

If `AUTH_ENABLED=false`, the app falls back to a local demo user so the UI remains usable before Entra is configured.
