# PharmaSignal

Real-Time Social Intelligence Platform for Patient Safety.
Monitors drug-related discussions across social platforms and applies NLP to detect adverse events.

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
├── backend/           # FastAPI + Celery (Python 3.11)
│   ├── api/routes/    # REST endpoints
│   ├── pipeline/      # 7-step NLP processing pipeline
│   ├── scrapers/      # Reddit, PubMed, FAERS, RSS, Twitter, Google News
│   ├── models/        # SQLAlchemy DB models + Pydantic schemas
│   ├── tasks/         # Celery async tasks
│   ├── agents/        # AI source discovery + copilot (Gemini Flash)
│   ├── knowledge/     # OpenFDA + RxNorm integrations
│   ├── main.py        # FastAPI entry point
│   ├── config.py      # App settings
│   ├── .env           # Secrets — edit before first run
│   └── requirements.txt
├── frontend/          # React 19 + Vite
│   ├── src/pages/     # Dashboard, Signals, Canvas, Admin, Reports…
│   ├── src/api/       # Axios API client
│   └── .env           # VITE_API_URL (default: http://localhost:8000)
└── docker-compose.yml # PostgreSQL + Redis + Celery services
```

---

## One-Time Setup

### 1 — Configure API keys

Edit `backend/.env`:

```env
# Required for AI Copilot — free key at https://aistudio.google.com/apikey
GEMINI_API_KEY=AIza...

# Required for Reddit scraping — https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=PharmaSignal/1.0 by YourUsername

# Optional — Twitter/X scraping
TWITTER_API_KEY=your_twitterapi_io_key
```

### 2 — Install backend dependencies (once)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate        # Linux / Mac
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3 — Install frontend dependencies (once)

```bash
cd frontend
npm install
```

---

## Running the Project

You need **4 things** running at the same time: Postgres + Redis, the API server, a Celery worker, and the frontend. Open 3 terminals.

### Terminal 1 — Start the database and message broker

```bash
# From the project root
docker compose up -d postgres redis
```

Wait until both are healthy (takes ~10 seconds):

```bash
docker compose ps
# NAME                   STATUS
# pharmasignal_db        running (healthy)
# pharmasignal_redis     running (healthy)
```

### Terminal 2 — Start the backend API

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The database schema is created automatically on first startup.
You should see: `Application startup complete.`

> API:       http://localhost:8000
> Swagger docs: http://localhost:8000/docs

### Terminal 3 — Start the Celery worker (background tasks)

```bash
cd backend
source .venv/bin/activate
celery -A tasks.celery_app worker --loglevel=info --concurrency=4 -Q celery,pipeline,scrape
```

You should see: `celery@... ready.`

### Terminal 4 — Start the frontend

```bash
cd frontend
npm run dev
```

> App: http://localhost:5173

All four are now running. Open http://localhost:5173 to use the app.

---

## Shutting Down

### Stop the frontend and backend (quick)

Press `Ctrl + C` in each terminal (frontend, API, Celery). That's enough to stop all Python and Node processes.

### Also stop the database and Redis

```bash
# From the project root
docker compose stop
```

This stops the containers but keeps all your data intact. Next time you run `docker compose up -d postgres redis`, all projects, signals, and posts are still there.

### Full shutdown — stop and remove containers (data is still safe)

```bash
docker compose down
```

Data is preserved in Docker volumes (`postgres_data`, `redis_data`). Running `docker compose up -d postgres redis` again restores everything.

---

## Deleting Data and Starting Fresh

Choose the level of reset you need:

---

### Level 1 — Delete a single project (from the UI)

1. Open http://localhost:5173
2. Go to **Projects**
3. Click the project you want to remove
4. Click **Delete project**

This removes the project and all its posts, signals, and canvas cards.

---

### Level 2 — Wipe all data, keep the schema

Use this to clear every project, post, and signal without touching the database schema (tables remain, ready to use immediately).

Make sure the backend is running, then:

```bash
docker exec -it pharmasignal_db psql -U pharmasignal -d pharmasignal -c "
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

---

### Level 3 — Complete wipe (schema + data + volumes)

Use this to go back to a completely blank slate — as if you just cloned the repo.

```bash
# 1. Stop everything (Ctrl+C in each terminal first, then:)
docker compose down -v
```

The `-v` flag deletes the Docker volumes, permanently removing all data.

```bash
# 2. Start fresh infrastructure
docker compose up -d postgres redis

# 3. Restart the backend (recreates schema automatically)
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 4. Restart Celery (new terminal)
cd backend && source .venv/bin/activate
celery -A tasks.celery_app worker --loglevel=info --concurrency=4 -Q celery,pipeline,scrape

# 5. Frontend was already running — no restart needed
```

You now have a completely empty database.

---

## Using the App

Once everything is running:

1. Go to http://localhost:5173
2. Create a **Project** — give it a name, add drug keywords (e.g. `ozempic`, `semaglutide`), pick sources (Reddit, RSS)
3. Click **Run Pipeline** — scrapes posts and runs the NLP pipeline
4. **Dashboard** — volume charts, sentiment, top symptoms
5. **Signals** — detected adverse events with severity (HIGH / MED / LOW); triage them manually or via AI
6. **AI Canvas** — click nodes in the knowledge graph to open the signal sidebar; use "Add as insight card" to build a canvas; ask the AI Copilot questions in the right panel
7. **Reports** — export a structured safety report
8. **Admin** — pipeline health, PII review queue, compliance settings

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
→ Make sure the Celery terminal is open and shows `celery@... ready.`

**AI Copilot says "requires a Gemini API key"**
→ Add `GEMINI_API_KEY=AIza...` to `backend/.env` and restart the backend.

**AI Copilot says "rate limit reached"**
→ Free Gemini tier quota is exhausted for today. It resets at midnight Pacific. All other features work normally.

**CORS errors in browser console**
→ The frontend URL must be in `CORS_ORIGINS` in `backend/config.py` (default includes `localhost:5173`).

**`docker compose down -v` deleted my data by mistake**
→ Unfortunately Docker volumes are not recoverable once deleted with `-v`. Always use `docker compose stop` (no `-v`) if you want to preserve data.
