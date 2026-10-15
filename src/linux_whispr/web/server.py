"""FastAPI web server for LinuxWhispr Dashboard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from linux_whispr.constants import VERSION
from linux_whispr.web.api.config_routes import router as config_router
from linux_whispr.web.api.dictionary_routes import router as dictionary_router
from linux_whispr.web.api.history_routes import router as history_router
from linux_whispr.web.api.models_routes import router as models_router
from linux_whispr.web.api.ollama_routes import router as ollama_router
from linux_whispr.web.api.snippets_routes import router as snippets_router
from linux_whispr.web.api.status_routes import router as status_router

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="LinuxWhispr Dashboard",
    version=VERSION,
    docs_url="/api/docs",
    redoc_url=None,
)


def set_runtime_status_provider(
    provider: Callable[[], dict[str, bool | str]] | None,
) -> None:
    """Attach the combined application's live runtime status to this dashboard."""
    app.state.runtime_status_provider = provider


def set_dictionary_provider(provider: Callable[[], object] | None) -> None:
    """Attach the combined application's live dictionary to this dashboard."""
    app.state.dictionary_provider = provider


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(status_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(dictionary_router, prefix="/api")
app.include_router(snippets_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(ollama_router, prefix="/api")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index() -> FileResponse:
    """Serve the SPA index page."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")
