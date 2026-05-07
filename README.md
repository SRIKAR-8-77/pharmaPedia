# Pharmapedia

> **Real-Time Social Listening Platform for Patient Safety & Pharmacovigilance**

Pharmapedia is a full-stack intelligence platform that continuously monitors social media, clinical databases, and online communities for early signals of adverse drug events, treatment dissatisfaction, and patient safety concerns — filling the gap between what patients say online and what gets captured in formal pharmacovigilance systems.

---

## The Problem We Solve

Healthcare institutions and pharma companies rely on voluntary adverse event reports (FAERS) and clinical trials for safety data. But patients talk about side effects on Reddit, Twitter, and health forums *months or years before* formal reports surface. Pharmapedia automates the listening, extraction, and analysis of this signal-rich patient-generated data — turning unstructured social content into structured, actionable safety intelligence.

---

## What We Built

### Part 1 — Generic Social Monitoring Engine

| Requirement | Implementation |
|-------------|---------------|
| Multi-project workspace | Project CRUD with keywords, date ranges, pause/resume state |
| Configurable keyword monitoring | Per-project keyword sets matched against all scraped content |
| Multiple source types | 7 scraper engines: Reddit, Twitter/X, PubMed, FAERS, Google News, RSS, Generic API |
| Per-source latency configuration | Real-time / Daily / Weekly scheduling via Celery Beat |
| Admin UI for source management | Full admin panel — add, edit, delete, test any source |
| Pluggable engine architecture | Factory-pattern scraper registry — new engines drop in as a single Python class |
| UI for project configuration | React 19 frontend with project wizard, source selector, alert rules |

### Part 2 — Analysis & Intelligence Layer

| Requirement | Implementation |
|-------------|---------------|
| Entity extraction | 7-step NLP pipeline: spaCy + scispaCy NER for drugs, symptoms, conditions |
| Individual content sentiment | VADER with medical term weights + HuggingFace RoBERTa transformer |
| Overall source sentiment & trends | Aggregated trend timelines per source and per drug |
| Safety & adverse event detection | Two-pass severity scoring (HIGH / MED / LOW) with causality analysis |
| Signal timeline view | Timeline dashboard with volume charts, spike detection, signal feed |
| Explainability & confidence scores | Every signal carries a confidence score, matched keywords, and extraction trace |
| PII / PHI flagging | Microsoft Presidio detects PERSON, EMAIL, PHONE, SSN, IP — routed to human review queue |
| Traceability | Full audit log: source → raw post → enriched post → signal → action |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Pharmapedia Platform                      │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │   React 19   │    │                FastAPI                    │  │
│  │   Frontend   │◄──►│  Projects · Signals · Canvas · Reports   │  │
│  │   (Vite)     │    │  Admin · Knowledge · Copilot · WebSocket  │  │
│  └──────────────┘    └──────────────┬───────────────────────────┘  │
│                                     │                               │
│  ┌──────────────────────────────────▼──────────────────────────┐   │
│  │                      Celery Task Queue (Redis)               │   │
│  │   Scrape Tasks   │   Pipeline Tasks   │   Report Generation  │   │
│  └────────┬─────────┴─────────┬──────────┴──────────┬──────────┘   │
│           │                   │                      │              │
│  ┌────────▼──────────┐  ┌────▼─────────────────┐   │              │
│  │  Scraper Registry │  │  7-Step NLP Pipeline  │   │              │
│  │  ─────────────── │  │  ─────────────────── │   │              │
│  │  Reddit (PRAW)    │  │  1. Clean + Lang Det  │   │              │
│  │  Twitter/X        │  │  2. PII Detection     │   │              │
│  │  PubMed (API)     │  │  3. NER Extraction    │   │              │
│  │  FAERS (FDA)      │  │  4. Sentiment Scoring │   │              │
│  │  Google News      │  │  5. Signal Detection  │   │              │
│  │  RSS Feeds        │  │  6. Deduplication     │   │              │
│  │  Generic API      │  │  7. Persist + Audit   │   │              │
│  └───────────────────┘  └──────────────────────┘   │              │
│                                                      │              │
│  ┌───────────────────────────────────────────────────▼──────────┐  │
│  │                     PostgreSQL (18 tables)                    │  │
│  │  Projects · Posts · Signals · PII Queue · Canvas · AuditLog  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────┐   ┌──────────────────────────────────┐   │
│  │   Knowledge Layer    │   │        AI / Agent Layer          │   │
│  │  OpenFDA drug labels │   │  Gemini Flash Copilot (4 tools)  │   │
│  │  RxNorm normalization│   │  Source Discovery Agent          │   │
│  │  MedDRA classification│  │  AI Triage Assistant             │   │
│  └──────────────────────┘   └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Differentiators

### 1. Pluggable Scraper Registry
Adding a new data source requires writing a single Python class that inherits from `BaseScraper`. The admin UI auto-discovers it and exposes it for project configuration — no core code changes needed.

```python
class MyForumScraper(BaseScraper):
    source_type = "my_forum"
    def fetch(self, keywords, config) -> list[RawPost]: ...
```

### 2. Pharmacovigilance-Grade Signal Detection
Our signal detection pipeline is deterministic and traceable by design — no LLM black-box in the hot path. Every detected signal carries:
- **Confidence score** (0.0–1.0) based on keyword density, entity presence, and syntactic patterns
- **Known vs. novel flag** — cross-referenced against OpenFDA drug labels to highlight truly new effects
- **Causality score** — proximity analysis of drug mentions to adverse effect mentions
- **MedDRA code** — standardized medical terminology classification

### 3. Privacy-First Architecture
PII/PHI is detected at ingestion (Step 2) before any analysis runs. Flagged content is routed to a human review queue with three actions: approve-redacted, delete, or mark-as-false-positive. All decisions are audit-logged.

### 4. AI-Augmented Triage (Agentic Capability)
The AI Copilot (Gemini Flash with function calling) can answer natural language questions like "Which drugs have the most HIGH severity signals this week?" or "Show me posts mentioning nausea for ozempic" — invoking structured backend tools to retrieve real data, not hallucinate it.

### 5. AI-Powered Source Discovery
An agentic source discovery module takes a drug name and automatically finds relevant Reddit communities, health forums, and online communities — then adds them to a project with one click.

### 6. Real-Time Signal Streaming
WebSocket endpoint streams newly detected signals to the dashboard in real time as the pipeline processes batches — no refresh needed.

### 7. Automated Intelligence Reports
Weekly automated reports aggregate signal trends, sentiment shifts, and novel adverse events into a structured safety summary with AI-generated narrative insights — exportable as HTML for regulatory submission workflows.

---

## Data Sources

| Source | Type | Auth | Content |
|--------|------|------|---------|
| **Reddit** | Social Forum | OAuth (PRAW) + RSS fallback | Patient communities, drug discussions |
| **Twitter / X** | Microblog | twitterapi.io key | Real-time drug mentions, hashtags |
| **PubMed** | Clinical Literature | Free API | Research abstracts, case reports |
| **FAERS** | Regulatory | Free FDA API | Official adverse event reports |
| **Google News** | News RSS | None | News articles about drugs/safety |
| **RSS Feeds** | Generic | None | Patient blogs, health forums |
| **Generic API** | Configurable | Optional | Any JSON API endpoint |

---

## NLP Pipeline (7 Steps)

```
Raw Post
  │
  ▼
Step 1: Clean        — HTML decode, URL/mention strip, language detection, length validation
  │
  ▼
Step 2: PII Detect   — Presidio: PERSON, EMAIL, PHONE, SSN, IP_ADDRESS → PII Queue
  │
  ▼
Step 3: NER Extract  — spaCy + scispaCy: drugs, symptoms, conditions + RxNorm normalization
  │
  ▼
Step 4: Sentiment    — VADER (medical weights) + HuggingFace RoBERTa (clinical transformer)
  │
  ▼
Step 5: Signal Det.  — Two-pass severity scoring, causality analysis, OpenFDA novelty check
  │
  ▼
Step 6: Dedup        — MinHash LSH (85% similarity threshold) — discard near-duplicates
  │
  ▼
Step 7: Persist      — EnrichedPost, SafetySignal, AuditLog written to PostgreSQL
```

---

## Features at a Glance

### Dashboard
- Real-time volume charts, sentiment distribution, signal severity breakdown
- Live signal feed (HIGH / MED / LOW) with drug and symptom tags
- One-click scrape trigger and pipeline run
- Spike detection alerts for sudden volume increases

### Signal Triage
- Filter signals by severity, drug, symptom, date range
- Manual triage actions: escalate, monitor, dismiss
- AI-assisted triage recommendations with explanation
- Confidence scores and extraction evidence for every signal

### AI Canvas (Knowledge Graph)
- Interactive node graph: drugs → symptoms → signals
- Click any node to open the signal detail sidebar
- "Add as insight card" to build a visual safety narrative
- AI Copilot panel for natural language querying

### Reports
- Generate structured safety reports with signal summaries
- AI-generated narrative: trends, emerging risks, recommendations
- HTML export ready for regulatory workflows
- Automated weekly digest scheduling

### Admin Panel
- Source management: add, edit, delete, test any scraper engine
- PII review queue with human-in-the-loop actions
- Pipeline health metrics: posts/hour, error rates, last run timestamps
- Compliance settings: data retention periods, GDPR erasure, audit log export

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.11) |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 15 (SQLAlchemy 2.0) |
| NLP | spaCy, scispaCy, VADER, HuggingFace Transformers |
| PII Detection | Microsoft Presidio |
| AI / Agents | Google Gemini Flash (function calling) |
| Drug Knowledge | OpenFDA API, RxNorm API |
| Medical Ontology | MedDRA (via terminology classification) |
| Deduplication | datasketch MinHash LSH |
| Frontend | React 19 + Vite |
| Charts | Recharts |
| Data Fetching | React Query + Axios |
| Containerization | Docker + Docker Compose |
| Deployment | Railway.app |

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker + Docker Compose | v24+ | https://docs.docker.com/get-docker/ |
| Python | 3.11+ | https://python.org |
| Node.js | 20+ | https://nodejs.org |

---

## Project Structure

```
PharmaPedia/
├── backend/
│   ├── api/routes/        # REST endpoints (projects, signals, canvas, admin, reports…)
│   ├── pipeline/          # 7-step NLP processing pipeline
│   ├── scrapers/          # Reddit, PubMed, FAERS, RSS, Twitter, Google News, Generic API
│   ├── models/            # SQLAlchemy DB models (18 tables) + Pydantic schemas
│   ├── tasks/             # Celery async tasks (scrape, pipeline, reports)
│   ├── agents/            # AI source discovery + copilot (Gemini Flash)
│   ├── knowledge/         # OpenFDA + RxNorm integrations
│   ├── main.py            # FastAPI entry point
│   ├── config.py          # App settings
│   ├── .env               # Secrets — edit before first run
│   └── requirements.txt
├── frontend/
│   ├── src/pages/         # Dashboard, Signals, Canvas, Admin, Reports, Projects
│   ├── src/components/    # Layout, EntityPill, SeverityBadge, Pagination
│   ├── src/api/           # Axios API client
│   └── .env               # VITE_API_URL (default: http://localhost:8000)
└── docker-compose.yml     # PostgreSQL + Redis + Celery services
```

---

## Quick Start

### Step 1 — Configure API keys

Copy and edit `backend/.env`:

```env
# Required for AI Copilot — free key at https://aistudio.google.com/apikey
GEMINI_API_KEY=AIza...

# Required for Reddit scraping — https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=Pharmapedia/1.0 by YourUsername

# Optional — Twitter/X scraping (twitterapi.io key)
TWITTER_API_KEY=your_twitterapi_io_key
```

### Step 2 — Install backend dependencies (once)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate        # Linux / Mac
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### Step 3 — Install frontend dependencies (once)

```bash
cd frontend
npm install
```

---

## Starting the Platform

You need **4 things** running simultaneously: Postgres + Redis, the API server, a Celery worker, and the frontend. Open 4 terminals.

### Terminal 1 — Infrastructure (database + message broker)

```bash
# From the project root
docker compose up -d postgres redis
```

Wait until both are healthy (~10 seconds):

```bash
docker compose ps
# NAME                   STATUS
# Pharmapedia_db        running (healthy)
# Pharmapedia_redis     running (healthy)
```

### Terminal 2 — Backend API

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The database schema is created automatically on first startup.
You should see: `Application startup complete.`

```
API:          http://localhost:8000
Swagger docs: http://localhost:8000/docs
```

### Terminal 3 — Celery worker (background tasks)

```bash
cd backend
source .venv/bin/activate
celery -A tasks.celery_app worker --loglevel=info --concurrency=4 -Q celery,pipeline,scrape
```

You should see: `celery@... ready.`

### Terminal 4 — Frontend

```bash
cd frontend
npm run dev
```

```
App: http://localhost:5173
```

All four are now running. Open **http://localhost:5173** to use the platform.

---

## Stopping the Platform

### Quick stop (keeps data)

Press `Ctrl + C` in each terminal (frontend, API, Celery worker), then:

```bash
# From the project root
docker compose stop
```

This stops the containers but preserves all your data. Running `docker compose up -d postgres redis` again restores everything exactly as you left it.

### Full stop (containers removed, data preserved)

```bash
docker compose down
```

Data is preserved in Docker volumes (`postgres_data`, `redis_data`).

---

## Resetting Data

### Level 1 — Delete a single project (from the UI)

1. Open http://localhost:5173
2. Go to **Projects**
3. Click the project → **Delete project**

This removes the project and all its posts, signals, and canvas cards.

### Level 2 — Wipe all data, keep the schema

```bash
docker exec -it Pharmapedia_db psql -U Pharmapedia -d Pharmapedia -c "
TRUNCATE TABLE audit_logs, canvas_states, safety_signals, enriched_posts,
               pii_queue, raw_posts, project_global_sources, source_configs,
               projects RESTART IDENTITY CASCADE;
"
```

Restart the backend after truncating:

```bash
# In the backend terminal: Ctrl+C, then
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Level 3 — Complete wipe (schema + data + volumes)

```bash
# 1. Stop everything (Ctrl+C in each terminal first)
docker compose down -v

# 2. Restart infrastructure
docker compose up -d postgres redis

# 3. Restart backend (recreates schema automatically)
cd backend && source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 4. Restart Celery (new terminal)
cd backend && source .venv/bin/activate
celery -A tasks.celery_app worker --loglevel=info --concurrency=4 -Q celery,pipeline,scrape

# 5. Frontend was already running — no restart needed
```

---

## Using the App

1. Open **http://localhost:5173**
2. Create a **Project** — add a name, drug keywords (e.g. `ozempic`, `semaglutide`), pick sources (Reddit, FAERS, RSS)
3. Click **Run Pipeline** — scrapes posts and runs the full NLP pipeline
4. **Dashboard** — volume charts, sentiment distribution, signal severity timeline
5. **Signals** — detected adverse events with severity (HIGH / MED / LOW); triage manually or via AI
6. **AI Canvas** — click nodes in the knowledge graph; use "Add as insight card" to build a visual safety narrative; ask the AI Copilot natural language questions in the right panel
7. **Reports** — generate and export a structured safety report as HTML
8. **Admin** — manage scraper sources, review PII queue, check pipeline health, configure compliance settings

---

## Environment Variables Reference

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL async URL (asyncpg) |
| `DATABASE_URL_SYNC` | Yes | PostgreSQL sync URL (Celery) |
| `REDIS_URL` | Yes | Redis connection URL |
| `GEMINI_API_KEY` | Yes | Google Gemini key — AI Copilot + triage |
| `REDDIT_CLIENT_ID` | Reddit only | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | Reddit only | Reddit app client secret |
| `TWITTER_API_KEY` | Twitter only | twitterapi.io key |
| `SECRET_KEY` | No | App secret (change in production) |

### `frontend/.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend API base URL |

---

## Troubleshooting

**Backend fails with `asyncpg connection refused`**
→ Postgres isn't healthy yet. Run `docker compose ps` and wait for `(healthy)`, then retry.

**`ModuleNotFoundError`**
→ You're not in the activated venv. Run `source backend/.venv/bin/activate` first.

**Celery tasks queue but never run**
→ Check `docker compose ps redis` shows `(healthy)`.
→ Make sure the Celery terminal shows `celery@... ready.`

**AI Copilot says "requires a Gemini API key"**
→ Add `GEMINI_API_KEY=AIza...` to `backend/.env` and restart the backend.

**AI Copilot says "rate limit reached"**
→ Free Gemini tier quota is exhausted for today. Resets at midnight Pacific. All other features work normally.

**CORS errors in browser console**
→ The frontend URL must be in `CORS_ORIGINS` in `backend/config.py` (default includes `localhost:5173`).

**`docker compose down -v` deleted my data by mistake**
→ Docker volumes are not recoverable once deleted with `-v`. Always use `docker compose stop` (without `-v`) to preserve data.

---

## Repository & Links

- **Repository:** https://github.com/SRIKAR-8-77/PharmaPedia
- **Live Demo:** Deployed on Railway.app
- **API Docs:** http://localhost:8000/docs (Swagger UI when running locally)
