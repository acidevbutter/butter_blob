from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.core.dependencies import DbSession
from app.core.exceptions import register_exception_handlers
from app.core.metrics import configure_metrics, emit_metrics
from app.core.storage import BlobStorageDep
from app.settings.config import settings
from app.settings.logging_config import setup_logging
from app.settings.middleware import register_middleware

setup_logging(settings.log_level)
configure_metrics()

app = FastAPI(
    title="Butter Blob",
    description="DevButter company-wide blob store: S3-backed file storage and serving.",
)
register_middleware(app)
register_exception_handlers(app)

# Domain routers (blobs, namespaces, admin, maintenance, public) are wired in by
# their implementation prompts (04+).


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["meta"])
async def readiness(db: DbSession, storage: BlobStorageDep) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        await emit_metrics([("HealthCheckFailure", 1, "Count")], {"Check": "database"})
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    if not await storage.bucket_exists():
        await emit_metrics([("HealthCheckFailure", 1, "Count")], {"Check": "storage"})
        raise HTTPException(status_code=503, detail="object storage unavailable")

    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
