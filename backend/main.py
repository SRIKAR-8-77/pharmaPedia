from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from models.database import init_db
from api.routes import projects, posts, pipeline, signals, canvas, copilot, admin, websocket, compliance, knowledge, reports, sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="PharmaSignal API",
    description="Real-Time Social Intelligence Platform for Patient Safety",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(posts.router, prefix="/projects", tags=["posts"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
app.include_router(signals.router, prefix="/projects", tags=["signals"])
app.include_router(canvas.router, prefix="/projects", tags=["canvas"])
app.include_router(copilot.router, prefix="/projects", tags=["copilot"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(compliance.router, prefix="/admin/compliance", tags=["compliance"])
app.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
app.include_router(reports.router, prefix="/projects", tags=["reports"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])
app.include_router(sources.router, prefix="/global-sources", tags=["global-sources"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
