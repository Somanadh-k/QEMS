# QEMS — Quality Error Management System

Two pieces, run together locally:

- [`backend/`](backend) — FastAPI + PostgreSQL + OpenAI. Architecture, database, core CRUD APIs,
  and AI integration. See [`backend/README.md`](backend/README.md) for the full write-up.
- [`frontend/`](frontend) — React (Vite), originally built against mock data by G. Hasini, now
  wired to the real backend. See [`frontend/README.md`](frontend/README.md) for exactly what
  changed to connect it.

## Running both together

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate   # after: python3 -m venv .venv && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev                 # after: npm install
```

Open `http://localhost:3000`. Log in with any seeded demo account (password `Password123!`):
`admin@qemscorp.dev`, `qa@qemscorp.dev`, `owner@qemscorp.dev`, `viewer@qemscorp.dev` — one per
role, from `backend/app/tasks/seed_users.py`.

Both `.env` files need to agree: the backend's `CORS_ORIGINS` must include the frontend's origin
(`http://localhost:3000` by default), and the frontend's `VITE_API_URL` must point at the
backend (`http://localhost:8000/api/v1` by default). Both `.env.example` files already have
matching defaults.

## First-time setup

```bash
# Database (PostgreSQL 15+ with the pgvector extension)
cd backend
cp .env.example .env        # edit DATABASE_URL, JWT_SECRET, OPENAI_API_KEY
alembic upgrade head
python -m app.tasks.seed          # roles, SLA policies, departments, categories
python -m app.tasks.seed_users    # one demo user per role

cd ../frontend
cp .env.example .env
npm install
```

## What's owned by whom

Per the project report's Section 16: G. Hasini built the frontend (UI/UX), A. Prashanth's module
was backend CRUD, and K. Somanadh owned architecture, database design, AI integration, and final
integration. Since only the frontend and this integration work were in progress when this was
picked up, the backend CRUD build (auth, error workflows, evidence, rebuttals, decisions) was
done here too — see `backend/README.md` for the full scope breakdown, including the one
deliberate deviation from the report (OpenAI instead of Gemini for every AI feature).
