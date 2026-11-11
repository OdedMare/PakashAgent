"""The organization's documents and rewritten prompts (D54)."""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import settings as settings_router
from app.bl import prompts
from app.bl.prompts import PromptLibrary, library as library_module
from app.common.errors import AppError, NotFoundError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, issue

SECRET = "test-secret"
PASSWORD = "settings-pass"


class FakeShared:
    """The two `deployment_state` calls, in memory."""

    def __init__(self):
        self.rows = {}
        self.down = False

    def deployment_value(self, key):
        if self.down:
            raise RuntimeError("database is down")
        return self.rows.get(key)

    def write_deployment_value(self, key, value):
        version = self.rows[key][0] + 1 if key in self.rows else 1
        self.rows[key] = (version, value)
        return version


@pytest.fixture
def shared():
    return FakeShared()


@pytest.fixture
def library(shared):
    library = PromptLibrary(shared)
    prompts.use(library)
    yield library
    prompts.use(None)


def test_with_nothing_saved_a_prompt_is_its_file(library):
    loaded = prompts.load("changes")

    prompts.use(None)
    assert loaded == prompts.load("changes")


def test_a_document_is_appended_to_every_loaded_prompt(library):
    library.save_document(None, "מילון היחידה", "סד״כ = מצבת כוח האדם", True)

    for name in ("manager_chat", "changes", "scheduler_directives"):
        text = prompts.load(name)
        assert text.endswith("### מילון היחידה\n\nסד״כ = מצבת כוח האדם")
        assert "## Organization knowledge" in text


def test_a_document_switched_off_is_kept_but_not_sent(library):
    saved = library.save_document(None, "טיוטה", "עוד לא מוכן", False)

    assert [row["title"] for row in saved["documents"]] == ["טיוטה"]
    assert "Organization knowledge" not in prompts.load("changes")


def test_a_document_is_edited_and_deleted_by_id(library):
    first = library.save_document(None, "א", "ראשון", True)["documents"][0]
    library.save_document(None, "ב", "שני", True)

    library.save_document(first["id"], "א", "נוסח-מתוקן", True)
    assert "נוסח-מתוקן" in prompts.load("changes")

    left = library.delete_document(first["id"])
    assert [row["title"] for row in left["documents"]] == ["ב"]
    assert "נוסח-מתוקן" not in prompts.load("changes")


def test_a_document_must_have_a_name_and_text_and_fit(library, monkeypatch):
    with pytest.raises(AppError):
        library.save_document(None, " ", "תוכן", True)
    with pytest.raises(AppError):
        library.save_document(None, "שם", "  ", True)
    with pytest.raises(AppError):
        library.save_document(
            None, "שם", "א" * (library_module.MAX_DOCUMENT_CHARS + 1), True,
        )
    with pytest.raises(NotFoundError):
        library.save_document("no-such-id", "שם", "תוכן", True)

    monkeypatch.setattr(library_module, "MAX_KNOWLEDGE_CHARS", 10)
    library.save_document(None, "א", "123456", True)
    with pytest.raises(AppError):
        library.save_document(None, "ב", "123456", True)
    # Switched off it rides on no call, so it fits.
    library.save_document(None, "ב", "123456", False)


def test_a_rewritten_prompt_replaces_the_file(library):
    saved = library.save_prompt("changes", "הנוסח שלנו")

    assert prompts.load("changes") == "הנוסח שלנו"
    entry = next(row for row in saved["prompts"] if row["name"] == "changes")
    assert entry["overridden"] and entry["text"] == "הנוסח שלנו"
    assert entry["default"] == prompts.default("changes").strip()
    assert not entry["default_changed"]


def test_a_rewritten_fragment_reaches_the_prompts_that_include_it(library):
    library.save_prompt("shared/hebrew", "## Language\n\nכתבו בעברית צבאית.")

    assert "כתבו בעברית צבאית." in prompts.load("manager_chat")


def test_a_rewrite_keeps_its_includes_working(library):
    library.save_prompt(
        "changes", "פתיחה\n\n<!-- include: shared/untrusted.md -->",
    )

    assert "## Untrusted input" in prompts.load("changes")


def test_a_rewrite_that_cannot_compose_is_refused(library):
    with pytest.raises(AppError):
        library.save_prompt("changes", "<!-- include: shared/missing.md -->")
    with pytest.raises(AppError):
        library.save_prompt("shared/hebrew", "<!-- include: shared/hebrew.md -->")
    with pytest.raises(AppError):
        library.save_prompt("changes", "   ")
    with pytest.raises(NotFoundError):
        library.save_prompt("../../main", "טקסט")

    assert prompts.load("changes") == prompts.compose("changes")


def test_resetting_goes_back_to_the_file(library):
    library.save_prompt("changes", "הנוסח שלנו")

    saved = library.reset_prompt("changes")

    assert prompts.load("changes") == prompts.compose("changes")
    assert not any(row["overridden"] for row in saved["prompts"])


def test_saving_the_shipped_text_stores_no_rewrite(library):
    saved = library.save_prompt("changes", prompts.default("changes"))

    assert not any(row["overridden"] for row in saved["prompts"])


def test_a_rewrite_says_when_the_shipped_text_moved_on(library, monkeypatch):
    library.save_prompt("changes", "הנוסח שלנו")
    monkeypatch.setattr(
        library_module._loader, "default", lambda name: "a newer release",
    )

    entry = next(
        row for row in library.describe()["prompts"] if row["name"] == "changes"
    )
    assert entry["default_changed"]


def test_a_save_in_one_process_reaches_another_at_its_next_poll(shared):
    here = PromptLibrary(shared)
    prompts.use(here)
    try:
        before = prompts.load("changes")
        PromptLibrary(shared).save_prompt("changes", "נשמר בתהליך אחר")

        # Loading asks the database nothing; the poll is what brings it.
        assert prompts.load("changes") == before
        here.poll()
        assert prompts.load("changes") == "נשמר בתהליך אחר"
    finally:
        prompts.use(None)


def test_an_unreachable_database_keeps_the_wording_held(library, shared):
    library.save_prompt("changes", "הנוסח שלנו")
    shared.down = True
    library.poll()

    assert prompts.load("changes") == "הנוסח שלנו"


def test_watching_polls_until_stopped(shared):
    import threading

    here = PromptLibrary(shared)
    PromptLibrary(shared).save_document(None, "מילון", "תוכן", True)
    stopped = threading.Event()
    thread = here.watch(stopped)
    stopped.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert "תוכן" in here.knowledge()


def test_the_compiler_id_follows_the_wording(library):
    from app.bl.compiled_sources.keys import compiler_id

    before = compiler_id()
    library.save_document(None, "מילון", "כונן = תורן בבית", True)

    # A standing rule translated under other definitions is translated again.
    assert compiler_id() != before


# --- the HTTP boundary -----------------------------------------------------


@pytest.fixture
def client(library):
    app = FastAPI()
    app.include_router(settings_router.build_router(
        None, None, Guards(SECRET), PASSWORD, library=library,
    ))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(COOKIE_NAME, issue(SECRET, "team-1", ROLE_BOSS, 1))
    return client


UNLOCKED = {settings_router.PASSWORD_HEADER: PASSWORD}


def test_the_library_is_behind_the_settings_password(client):
    assert client.get("/api/settings/library").status_code == 403
    assert client.post(
        "/api/settings/library/documents", json={"title": "א", "content": "ב"},
    ).status_code == 403
    assert client.put(
        "/api/settings/library/prompts/changes", json={"text": "ג"},
    ).status_code == 403


def test_documents_over_http(client):
    created = client.post(
        "/api/settings/library/documents", headers=UNLOCKED,
        json={"title": "מילון", "content": "מ״מ = מפקד משמרת"},
    ).json()
    document = created["documents"][0]
    assert document["enabled"] and created["knowledge_chars"] == len("מ״מ = מפקד משמרת")

    updated = client.put(
        "/api/settings/library/documents/" + document["id"], headers=UNLOCKED,
        json={"title": "מילון", "content": "חדש", "enabled": False},
    ).json()
    assert updated["documents"][0]["content"] == "חדש"
    assert updated["knowledge_chars"] == 0

    assert client.put(
        "/api/settings/library/documents/nope", headers=UNLOCKED,
        json={"title": "מילון", "content": "חדש"},
    ).status_code == 404
    assert client.post(
        "/api/settings/library/documents", headers=UNLOCKED,
        json={"title": "", "content": "חדש"},
    ).status_code == 400

    left = client.delete(
        "/api/settings/library/documents/" + document["id"], headers=UNLOCKED,
    ).json()
    assert left["documents"] == []


def test_prompts_over_http_including_a_fragment_with_a_slash(client):
    listed = client.get("/api/settings/library", headers=UNLOCKED).json()
    assert [row["name"] for row in listed["prompts"]][:2] == ["manager_chat", "changes"]

    saved = client.put(
        "/api/settings/library/prompts/shared/hebrew", headers=UNLOCKED,
        json={"text": "## Language\n\nעברית."},
    ).json()
    assert next(
        row for row in saved["prompts"] if row["name"] == "shared/hebrew"
    )["overridden"]

    reset = client.delete(
        "/api/settings/library/prompts/shared/hebrew", headers=UNLOCKED,
    ).json()
    assert not any(row["overridden"] for row in reset["prompts"])

    assert client.put(
        "/api/settings/library/prompts/no_such", headers=UNLOCKED,
        json={"text": "x"},
    ).status_code == 404
