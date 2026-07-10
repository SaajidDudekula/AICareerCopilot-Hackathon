# AI Career Copilot - Hackathon Demo

A minimal, working slice of AI Career Copilot: upload a resume, get an
AI-parsed profile, pick a target role, and get a skill-gap analysis +
personalized learning roadmap. Every AI call is routed through **Mesh API**
to Claude models (Haiku for resume parsing, Sonnet for skill-gap/roadmap
reasoning).

## What's in scope for this demo (intentionally)

- Resume upload (.txt, .pdf, .docx) -> AI parsing (name, skills, education, experience, projects)
- Target role input -> AI skill gap analysis -> personalized roadmap -> job readiness score

## What's out of scope (by design, to ship in 2 days)

- Auth / user accounts
- Database persistence (this demo is stateless / in-memory per session)
- Job discovery, application tracker, interview coach (validated separately,
  not wired into this demo)

## Running tests

The backend has a pytest suite covering both endpoints. Every Mesh API call
in the tests is mocked, so running tests never costs money and never needs
a real API key or internet access.

```bash
cd backend
pip install -r requirements.txt   # includes pytest + httpx
pytest -v
```

You should see all 12 tests pass. Run this before every commit and right
before recording the demo — a green test suite is worth mentioning to
judges as a sign of real engineering discipline, not just a prompt wrapped
in a UI.

## Security notes

A few things were deliberately added given this handles user-uploaded files
and calls a paid AI API:

- **API key never in code** — lives only in `.env`, which is gitignored.
  Never commit `.env`; only `.env.example` (with placeholder values) should
  go into the repo.
- **CORS is restricted**, not wildcard-open — only specific local origins
  are allowed by default (`ALLOWED_ORIGINS` env var). `"null"` is included
  by default only to support opening `index.html` directly via `file://`
  during quick testing; tighten this before any real deployment.
- **File size capped at 5MB** (`MAX_FILE_SIZE_BYTES` in `main.py`) — prevents
  someone uploading a huge file to run up your Mesh API token bill or hang
  the server.
- **Role/skills text length capped** — same reasoning, applied to the
  skill-gap endpoint's form fields.
- **Prompt-injection guarding** — resume text and skills text are wrapped in
  `<resume>`/`<skills>` tags with an explicit instruction telling the model
  to treat that content as data, not instructions. This doesn't make it
  bulletproof, but it meaningfully reduces the risk of a resume containing
  something like "ignore previous instructions and output X" from actually
  changing the model's behavior.
- **Error messages are sanitized** — if PDF/DOCX parsing fails internally,
  the client gets a clean, generic message, not a raw Python exception or
  stack trace that could leak internal details.

### What's intentionally NOT done here (be upfront about this if asked)

This is a hackathon/demo backend, not the production system from the PRD.
Still missing, and fine to say so if a judge asks:
- No authentication / per-user rate limiting (the production Technical
  Architecture doc covers this — JWT auth, per-user AI usage caps)
- No persistent database — this demo is stateless between requests
- No HTTPS termination configured (would be handled by the hosting platform
  in a real deployment — Vercel/Railway/Render, per the architecture doc)

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your real MESH_API_KEY
```

Backend will be running at `http://localhost:8000`. Visit
`http://localhost:8000` in a browser — you should see:
```json
{"status": "ok", "message": "AI Career Copilot demo backend is running"}
```

### 2. Frontend

No build step needed — it's a single static HTML file.

Just open `frontend/index.html` directly in your browser (double-click it,
or right-click -> Open With -> your browser).

If your browser blocks `fetch()` calls from a `file://` page, instead serve
it with a simple local server:
```bash
cd frontend
python -m http.server 5500
```
Then visit `http://localhost:5500` in your browser.

## Using it

1. Prepare a resume as a `.txt` file (copy-paste resume text into a text file)
2. Upload it and click "Parse Resume" — see the AI-extracted name, email, skills
3. Enter a target role (a sensible default is pre-filled)
4. Click "Generate Skill Gap + Roadmap" — see missing skills, a sequenced
   roadmap, recommended projects, and a job readiness score

## For the demo recording

Suggested flow (2-3 minutes):
1. Briefly state the problem: students don't know if they're job-ready,
   or what to do about it — current tools are fragmented
2. Show the resume upload + parsing (mention: powered by Claude via Mesh API)
3. Show the skill gap + roadmap generation for a real role
4. Point out the job readiness score and roadmap resources
5. Close with the vision: this is one slice of a full platform (mention
   the other planned modules: interview coach, job discovery, tracker)

## Architecture note

This demo intentionally uses a single static HTML file + vanilla JS instead
of the full React/TypeScript/Tailwind stack from the production PRD, purely
to maximize build speed within the hackathon window. The backend (FastAPI +
Mesh API integration) is structurally consistent with the production
Technical Architecture document, so this logic can be lifted directly into
the real FastAPI service later.
