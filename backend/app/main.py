"""FastAPI composition root."""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.dependencies import Guards
from app.api.routers import (
    employee, health, interview, schedules, settings, workspace,
)
from app.bl.employee_service import EmployeeService
from app.bl.interview_service import InterviewService
from app.bl.schedule_service import ScheduleService
from app.bl.workspace_service import WorkspaceService
from app.common.config.settings import Settings
from app.common.errors import AppError
from app.common.logging_setup import configure_logging
from app.common.sessions import generate_secret
from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)
from app.dal.llm.openai_client import OpenAIJsonClient
from app.dal.repository import Repository

# Before anything else constructs a logger, so no start-up line is lost.
configure_logging()
_log = logging.getLogger("pakash.api")

def _worker_count() -> int:
    """How many workers this process is one of, as the server was told.

    Read from the environment rather than from uvicorn: by the time this
    module is imported the worker is already forked and has no handle on the
    parent's arguments. Both spellings are checked because `WEB_CONCURRENCY`
    is what uvicorn and gunicorn both honour, while `UVICORN_WORKERS` is what
    a compose file is likely to say.
    """
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        try:
            count = int(os.getenv(name, ""))
        except ValueError:
            continue
        if count > 0:
            return count
    return 1


env = Settings()
store = RuntimeSettingsStore(env)
repository = Repository(store)
llm = OpenAIJsonClient(store)
interview_service = InterviewService(repository, llm)
workspace_service = WorkspaceService(repository)
schedule_service = ScheduleService(repository, llm)
# Takes the schedule service, not just the repository: the personal view needs
# an audited schedule, and recomputing the audit for the employee would be a
# second implementation of the arithmetic the manager sees (D14).
employee_service = EmployeeService(repository, schedule_service)

# An unset secret is generated per process. Fine for a single-worker dev run,
# wrong for a multi-worker deployment — each worker would sign with its own
# key and reject the others' cookies, logging bosses out at random. Warned
# about rather than defaulted to a constant, since a hardcoded fallback
# secret is the version of this that fails silently and forever.
session_secret = env.session_secret or generate_secret()
if not env.session_secret:
    # Refused rather than warned about when there is more than one worker.
    # The symptom is bosses being logged out at random with every request
    # that happens to land on a different worker — which reads as a session
    # bug, not as a missing environment variable, and costs hours to trace
    # back to here. A start-up that fails with the variable's name in the
    # message costs seconds.
    if _worker_count() > 1:
        raise RuntimeError(
            "PAKASH_SESSION_SECRET must be set when running more than one "
            "worker: each worker would sign session cookies with its own "
            "generated key and reject every cookie signed by the others. "
            "Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    _log.warning(
        "PAKASH_SESSION_SECRET is not set; generated one for this process. "
        "Sessions will not survive a restart and will break across workers."
    )
guards = Guards(session_secret)

app = FastAPI(
    title="PakashAgent",
    version="0.1.0",
    description="סוכן שבונה ומתחזק סידורי עבודה בשיחה",
)

app.include_router(health.build_router(repository))
app.include_router(
    workspace.build_router(
        workspace_service, guards, session_secret, env.session_days
    )
)
app.include_router(interview.build_router(interview_service, guards))
app.include_router(schedules.build_router(schedule_service, guards))
app.include_router(settings.build_router(store, llm, guards))
app.include_router(
    employee.build_router(
        employee_service, guards, session_secret, env.session_days
    )
)
# The manager's side of constraint requests. A separate router so that every
# route on it depends on `boss` visibly, rather than sitting next to the
# employee-guarded ones.
app.include_router(employee.build_manager_router(employee_service, guards))


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
