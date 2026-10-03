"""DAT — AI Data Analytics backend (FastAPI)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analysis, assistant, auth, datasets, health, insights, visualization
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("main")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI-powered data analytics platform — ingestion, profiling, "
                "visualization, insights, and the AnalytIQ Assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.api_prefix
app.include_router(health.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)
app.include_router(datasets.router, prefix=prefix)
app.include_router(analysis.router, prefix=prefix)
app.include_router(visualization.router, prefix=prefix)
app.include_router(insights.router, prefix=prefix)
app.include_router(assistant.router, prefix=prefix)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Full detail goes to server logs only; the client gets a clean, branded
    # message — never a stack trace, SQL error, or internal path.
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong on our end. Please try again.",
            }
        },
    )


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "health": f"{prefix}/health"}
