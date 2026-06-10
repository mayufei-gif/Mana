from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import chapters, highlights, jobs, notes, search, settings as settings_router, subtitles, videos
from .services.queue_service import runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    runtime.start()
    yield
    runtime.stop()


app = FastAPI(title="CourseMind NAS", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(subtitles.router)
app.include_router(chapters.router)
app.include_router(highlights.router)
app.include_router(notes.router)
app.include_router(search.router)
app.include_router(settings_router.router)
app.include_router(jobs.router)


@app.get("/")
def root() -> dict:
    return {"ok": True, "name": "CourseMind NAS", "version": "0.1.0"}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
