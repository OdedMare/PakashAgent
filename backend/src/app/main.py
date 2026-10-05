"""FastAPI composition root."""

import logging
import os
import secrets

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.dependencies import Guards
from app.api.routers import (
    copilot, employee, health, interview, profile, schedules, settings,
    workspace,
)
from app.bl.copilot import CopilotService
from app.bl.employee_service import EmployeeService
from app.bl.interview_service import InterviewService
from app.bl.profile_service import ProfileService
from app.bl.schedule_service import ScheduleService
from app.bl.workspace_service import WorkspaceService
from app.common.config.settings import Settings
from app.common.errors import AppError, error_payload
from app.common.logging_setup import configure_logging
from app.common.sessions import generate_secret
from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)
from app.dal.database.postgres import close_pool
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
# Handed the settings store, not just the repository: `schedule_generation_mode`
# is read when a period is opened, so a mode saved in the panel applies to the
# next build with no restart — the same property the model settings have.
schedule_service = ScheduleService(repository, llm, settings=store)
profile_service = ProfileService(repository)
copilot_service = CopilotService(
    repository, schedule_service, interview_service
)
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
app.include_router(profile.build_router(profile_service, guards))
app.include_router(settings.build_router(store, llm, guards))
app.include_router(copilot.build_router(copilot_service, repository, guards))
app.include_router(
    employee.build_router(
        employee_service, guards, session_secret, env.session_days
    )
)
# The manager's side of constraint requests. A separate router so that every
# route on it depends on `boss` visibly, rather than sitting next to the
# employee-guarded ones.
app.include_router(employee.build_manager_router(employee_service, guards))
# The manager's side of swaps, on its own prefix. Kept apart from the router
# above so `/{request_id}` and `/{swap_id}` cannot shadow each other, and so
# the `boss` guard stays visible on every route of both.
app.include_router(employee.build_swap_router(employee_service, guards))


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


@app.on_event("shutdown")
def shutdown() -> None:
    """Return every pooled connection before the process goes away.

    Without this the pool's own worker threads outlive the shutdown and
    Postgres is left holding connections until it times them out — visible as
    a server that slowly accumulates idle backends across restarts.
    """
    close_pool()


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError) -> JSONResponse:
    """`AgentError` and friends carry Hebrew copy meant for the boss."""
    _log.warning(
        "AppError %s %s -> %s: %s",
        request.method, request.url.path, exc.status_code, exc,
    )
    return JSONResponse(
        status_code=exc.status_code, content=error_payload(exc)
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc: Exception) -> JSONResponse:
    """Anything that is not an `AppError`, with the cause kept.

    Without this, an exception nobody anticipated left as Starlette's default
    500, whose body carries no `detail` at all. The frontend reads `detail`
    and falls through to `שגיאת שרת (500)` — a status code, which tells the
    manager nothing and tells us nothing either, because the traceback was
    never logged. That is precisely how a slow model, an exhausted connection
    pool and a genuine bug all became the same unreadable screen.

    So: log the traceback with the route that produced it, and answer with a
    Hebrew sentence plus a short `error_id` that appears in both places. The
    manager reads the sentence and can quote the id; we grep the log for it
    and land on the exact stack.

    **The id is random, never the exception text.** `str(exc)` on a database
    or driver error can carry a connection string, a query with employee
    names in it, or a file path — none of which belongs on a manager's
    screen (backend/CLAUDE.md). It goes to the log, which is ours.

    `AppError` is handled above and never reaches here; FastAPI matches the
    most specific registered handler.
    """
    error_id = secrets.token_hex(4)
    _log.exception(
        "unhandled %s %s error_id=%s", request.method, request.url.path,
        error_id,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "שגיאה לא צפויה בשרת. מספר לאיתור: %s" % error_id
            ),
            "error_id": error_id,
        },
    )
