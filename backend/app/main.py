"""FastAPI composition root."""

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.routers import health, interview
from app.bl.interview_service import InterviewService
from app.common.config.settings import Settings
from app.common.errors import AppError
from app.common.logging_setup import configure_logging
from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)
from app.dal.llm.openai_client import OpenAIJsonClient
from app.dal.repository import Repository

# Before anything else constructs a logger, so no start-up line is lost.
configure_logging()
_log = logging.getLogger("pakash.api")

env = Settings()
store = RuntimeSettingsStore(env)
repository = Repository(store)
llm = OpenAIJsonClient(store)
interview_service = InterviewService(repository, llm)

app = FastAPI(
    title="PakashAgent",
    version="0.1.0",
    description="סוכן שבונה ומתחזק סידורי עבודה בשיחה",
)

app.include_router(health.build_router(repository))
app.include_router(interview.build_router(interview_service))


@app.on_event("startup")
def startup() -> None:
    """Create the schema and tables if they are not there yet.

    A database that is not up yet must not take the process down with it —
    the health route is the thing that reports it, and it can only answer if
    the app finished starting.
    """
    try:
        repository.initialize()
    except Exception as exc:
        _log.error("database initialization failed: %s", exc)


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError) -> JSONResponse:
    """`AgentError` and friends carry Hebrew copy meant for the boss."""
    _log.warning(
        "AppError %s %s -> %s: %s",
        request.method, request.url.path, exc.status_code, exc,
    )
    return JSONResponse(
        status_code=exc.status_code, content={"detail": str(exc)}
    )
