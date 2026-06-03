from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog
import app.models  # noqa


from app.core.config import settings
from app.api.v1 import api_router
from app.db.session import init_db
from app.db.redis import close_redis

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up", environment=settings.ENVIRONMENT)
    if not settings.is_production:
        await init_db()   # dev-only auto-create; use Alembic in prod
    yield
    await close_redis()
    log.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o) for o in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*.run.app", "yourdomain.com"])

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": settings.VERSION, "env": settings.ENVIRONMENT}
