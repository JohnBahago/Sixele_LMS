# Sixele LMS Backend

FastAPI + MongoDB backend for Sixele LMS.

## Run locally

1. Create a virtual environment:
   `python -m venv .venv`
2. Activate it.
3. Install dependencies:
   `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and configure MongoDB/JWT settings.
5. Start the API:
   `uvicorn app.main:app --reload --port 8000`

API docs: `http://localhost:8000/docs`

## Initial endpoints

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/roles`
- `POST /api/roles`

This is the foundation. Authorization will be expanded into a central permission catalog and scope-aware permission service before the LMS modules are implemented.
