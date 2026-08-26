import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routes import chat, feedback, documents, sources, releases, links, kbs, kb_upload
from .services.security import limiter, rate_limit_handler, RateLimitExceeded

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = logging.DEBUG if settings.ENVIRONMENT.upper() == "DEV" else logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Joule Verne API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


# ---------------------------------------------------------------------------
# Cache-Control middleware for static assets
# ---------------------------------------------------------------------------


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Add Cache-Control headers for Vite-hashed static assets (immutable)."""
    response: Response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


# Routers
app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(documents.router)
app.include_router(sources.router)
app.include_router(releases.router)
app.include_router(links.router)
app.include_router(kbs.router)
app.include_router(kb_upload.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/v1/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static files (Vue frontend) — must be last to avoid catching API routes
# ---------------------------------------------------------------------------

_static_dir = Path(__file__).parent.parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
