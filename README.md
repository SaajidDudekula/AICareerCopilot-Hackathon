# AI Career Copilot

An AI-powered career mentor: upload a resume, get an AI-parsed profile, see
a skill-gap analysis against your target role, follow a personalized
learning roadmap, and practice with a real multi-turn AI mock interview
that scores you at the end. Every AI call is routed through **Mesh API**
to Claude models — Haiku for resume parsing (cheap, fast, structured
extraction), Sonnet for skill-gap reasoning and interview conversation
(higher-quality reasoning where it actually matters).

Originally built as a 2-day Mesh API Hackathon submission, then extended
into a real, persistent, authenticated product — this is no longer a
stateless demo.

## What's built

- **Authentication** — email/password (bcrypt-hashed) and Google OAuth,
  both issuing JWT access + refresh tokens. Login attempts are rate-limited
  against brute-forcing.
- **Resume upload & parsing** — .txt, .pdf, .docx supported. Extracts name,
  email, skills, education, experience, projects, certifications. Persisted
  to the database under the logged-in user.
- **Skill gap analysis + roadmap** — compares parsed skills against a
  target role, returns missing skills (prioritized), a sequenced learning
  roadmap, recommended projects, and a job readiness score. Persisted and
  linked back to the resume it was generated from.
- **AI Interview Coach** — a real 4-question mock interview (behavioral,
  2x technical/conceptual, problem-solving), with feedback after each
  answer and a final persisted report: score out of 10, strengths, and
  improvement points.
- **Database** — PostgreSQL (Neon). Tables: `users`, `resumes`,
  `resume_analyses`, `mock_interviews`, `interview_reports`.

## What's NOT built yet

- Career chatbot (cost-tested, not wired into a real endpoint)
- Job discovery / application tracker
- ATS resume score as a distinct feature (currently only extraction happens)
- Production frontend (React/TypeScript/Tailwind per the original PRD) —
  current frontend is a single static HTML/CSS/JS page, intentionally kept
  simple to move fast
- Database migrations (Alembic) — schema changes currently require
  dropping and recreating tables, which destroys data. Fine while there's
  no real user data; needs fixing before any real users exist.

## Project structure

```
backend/
  main.py              - resume parsing + skill-gap endpoints
  auth.py               - password hashing, JWT creation/verification, rate limiting
  auth_routes.py         - /api/auth/register, /login, /google, /refresh, /me
  interview_routes.py    - /api/interview/start, /answer, /{id}/report
  mesh_client.py         - shared Mesh API client setup
  database.py            - SQLAlchemy engine/session setup
  models.py              - User, Resume, ResumeAnalysis, MockInterview, InterviewReport
  schemas.py              - Pydantic request/response validation
  init_db.py              - one-time script to create tables in Neon
  security_test.py        - live security test suite (run against a running backend)
  requirements.txt
  .env.example
  tests/
    conftest.py
    test_main.py          - pytest suite, all external calls mocked

frontend/
  index.html
  styles.css              - glassmorphic theme
  config.js               - non-secret frontend config (API_BASE, Google Client ID)
```

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `MESH_API_KEY` | app.meshapi.ai -> API Keys |
| `DATABASE_URL` | Neon project -> Connect |
| `JWT_SECRET_KEY` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console -> APIs & Services -> Credentials |

Then create the database tables (safe to re-run — only creates tables that
don't already exist):
```bash
python init_db.py
```

Start the server:
```bash
uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000` — you should see:
```json
{"status": "ok", "message": "AI Career Copilot demo backend is running"}
```
Visit `http://localhost:8000/docs` to see the full interactive API reference
(all endpoints, request/response shapes).

### 2. Frontend

Open `config.js` and set your real Google Client ID (must match the one in
your backend `.env`).

Serve it with a simple local server (don't just double-click `index.html` —
Google Sign-In needs a real origin, not `file://`):
```bash
cd frontend
python -m http.server 5500
```
Visit `http://localhost:5500`.

**Important:** whatever origin you actually browse from (`localhost:5500`
vs `127.0.0.1:5500` — these count as different origins to Google) must be
added under "Authorized JavaScript origins" in your Google Cloud Console
OAuth client settings.

## Using it

1. Register (email/password) or sign in with Google
2. Upload a resume (.txt, .pdf, or .docx) -> see the AI-parsed profile
3. Enter a target role -> generate skill gap + roadmap -> see missing
   skills, roadmap steps, recommended projects, job readiness score
4. Click "Continue to Mock Interview" -> answer 4 questions -> get a
   scored report with strengths and improvement points

## Running tests

```bash
cd backend
pytest -v
```

All external calls (Mesh API, database) are mocked using FastAPI's
`dependency_overrides` and `unittest.mock` — this suite never costs real
money, never needs a real database connection, and never needs a real API
key beyond a dummy value set in `tests/conftest.py`. Should show all tests
passing (27 at last count — auth requirements, cross-user isolation,
input validation, error handling, and the full interview start-to-report
flow are all covered).

## Running the live security test suite

Unlike the pytest suite (which mocks everything), `security_test.py` hits
your **actual running backend** with real HTTP requests — rate limiting,
JWT tampering, cross-user data access attempts, malformed input, and error
message sanitization.

```bash
# Make sure uvicorn is running first, in another terminal
cd backend
python security_test.py
```

This creates two throwaway test users and makes a small number of real
Mesh API calls (expect roughly Rs 3-5 of real spend per run) — not
something to run in a tight loop repeatedly, but a good pre-deploy or
post-change sanity check.

## Security notes

- **Secrets never in code.** `MESH_API_KEY`, `DATABASE_URL`, `JWT_SECRET_KEY`
  live only in `backend/.env`, which is gitignored. Only `.env.example`
  (placeholder values) belongs in the repo. The Google Client ID is the one
  exception that's safe to commit in `frontend/config.js` — Client IDs are
  designed to be public; Google's origin-checking (not secrecy of the ID)
  is what actually protects the OAuth flow.
- **Passwords are bcrypt-hashed**, never stored or logged in plain text.
- **JWT access/refresh token pattern** — short-lived access tokens (30 min
  default), longer refresh tokens (7 days default), separately signed and
  verified.
- **Login rate limiting** — 5 failed attempts locks out further attempts
  for 15 minutes (in-memory; fine for a single instance, would need
  Redis-backed limiting before running multiple backend instances).
- **CORS is restricted**, not wildcard-open — configurable via
  `ALLOWED_ORIGINS`.
- **File size capped at 5MB**, role/skill/answer text length capped —
  prevents abuse from running up Mesh API costs or hanging the server.
- **Prompt-injection guarding** — user-submitted resume/skills text is
  wrapped in tags with explicit instructions telling the model to treat it
  as data, not instructions.
- **Cross-user data isolation** — every resource lookup (resumes, skill-gap
  analyses, interviews) verifies the requesting user actually owns that
  resource before returning or linking anything.
- **Malformed IDs return clean 404s, not raw database errors** — IDs are
  validated as syntactically correct UUIDs before ever reaching a database
  query, so a garbled ID can't crash the query layer.
- **Error messages are sanitized** — corrupted file uploads, invalid model
  output, etc. return clean, generic messages, never a raw Python traceback.

## Architecture note

The frontend intentionally stays a single static HTML/CSS/JS page rather
than the full React/TypeScript/Tailwind stack from the original PRD, to
keep moving fast. The backend (FastAPI + SQLAlchemy + Mesh API) is
structurally consistent with the production Technical Architecture
document, so this logic can be lifted into the full production build
later without a rewrite.
