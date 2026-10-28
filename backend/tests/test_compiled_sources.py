"""Standing sources translated once and kept (D32): the cache, time, and the save hook."""

import json

from app.bl.compiled_sources import NullCache, SourceCompiler, TranslationCache, report
from app.bl.compiled_sources.timing import UNREAD_TIME, mentioned_dates
from app.bl.solver import generate_span
from app.bl.directive_agent import DirectiveAgent
from app.bl.profile_service import ProfileService
from app.bl.scheduler.scheduler import Scheduler
from app.common.errors import AgentError

import datetime

MORNING, NIGHT = "בוקר", "לילה"
TEAM = "team-1"
WRITTEN = "2026-10-20"  # A Tuesday.
WEEK = ("2026-10-18", "2026-10-24")
NEXT_WEEK = ("2026-10-25", "2026-10-31")


def _profile(rules=(), notes=None, employees=("דנה", "יוסי", "עודד"), **extra):
    people = [{"name": name, **({"notes": notes[name]} if notes and name in notes else {})}
              for name in employees]
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": people,
        "rules": [{"text": text, "priority": "soft"} for text in rules],
        "shifts": [
            {"name": MORNING, "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
            {"name": NIGHT, "start_time": "23:00", "end_time": "07:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }
    profile.update(extra)
    return profile


class _Repository:
    """The compiled-sources half of the repository, plus what the hooks read."""

    def __init__(self, profile=None):
        self.profile = profile or _profile()
        self.rows, self.anchors, self.jobs = {}, {}, []

    def team_profile(self, team_id):
        return self.profile

    def team_profile_revision(self, team_id):
        return None if self.profile is None else 0

    def update_team_profile(self, team_id, profile, expected_revision=None):
        self.profile = profile
        return profile

    def preferences(self, team_id, status=None):
        return []

    def enqueue_copilot_job(self, team_id, dedupe_key, kind="scan", payload=None):
        if any(job["key"] == dedupe_key for job in self.jobs):
            return None
        self.jobs.append({"key": dedupe_key, "kind": kind})
        return self.jobs[-1]

    def compiled_sources(self, team_id, vocab_key, compiler, source_keys):
        return [dict(row) for (team, key, vocab, comp), row in self.rows.items()
                if team == team_id and vocab == vocab_key and comp == compiler
                and key in source_keys]

    def save_compiled_sources(self, team_id, vocab_key, compiler, rows):
        for row in rows:
            self.rows[(team_id, row["source_key"], vocab_key, compiler)] = json.loads(json.dumps(row))

    def touch_compiled_sources(self, team_id, source_keys):
        pass

    def prune_compiled_sources(self, team_id, days=90):
        pass

    def source_anchors(self, team_id, source_keys, today):
        for key in source_keys:
            self.anchors.setdefault(key, today)
        return {key: self.anchors[key] for key in source_keys}


class _Llm:
    def __init__(self, *answers):
        self.answers, self.payloads = list(answers), []

    def complete_json(self, system, user, schema=None, **kwargs):
        self.payloads.append(json.loads(user))
        if not self.answers:
            raise AssertionError("an unexpected model call")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _answer(requests=(), unresolved=(), timing=(), directives=(), tokens=100):
    return {"calls": [], "directives": list(directives), "requests": list(requests),
            "unresolved": list(unresolved), "timing": list(timing),
            "_usage": {"prompt_tokens": tokens - 20, "completion_tokens": 20,
                       "total_tokens": tokens}}


def _avoid(source="source-1", employee="דנה", hard=False, dates=(), weekdays=("שני",),
           shifts=(NIGHT,), weight=1, reason="עדיף בלי לילות שני"):
    return {"source_id": source, "kind": "avoid", "employees": [employee],
            "shifts": list(shifts), "dates": list(dates), "weekdays": list(weekdays),
            "count": None, "per": "period", "is_hard": hard, "weight": weight, "reason": reason}


def _timing(source="source-1", kind="none", starts="", ends="", maybe="", question=""):
    return {"source_id": source, "kind": kind, "phrase": "", "starts_on": starts,
            "ends_on": ends, "maybe_through": maybe, "question": question}


def _cache(repository, today=WRITTEN):
    return TranslationCache(repository, TEAM, today=today)


def _translate(llm, repository, week=WEEK, **kwargs):
    return DirectiveAgent(llm).translate(repository.profile, *week,
                                         cache=_cache(repository), **kwargs)


RULE = "עדיף שדנה לא תעבוד בלילות שני"


def test_a_standing_rule_is_translated_once_and_loaded_after():
    repository = _Repository(_profile(rules=[RULE]))
    llm = _Llm(_answer([_avoid()], timing=[_timing()]))

    first = _translate(llm, repository)
    second = _translate(llm, repository, week=NEXT_WEEK)

    assert len(llm.payloads) == 1
    assert llm.payloads[0]["sources"][0]["mode"] == "compile"
    assert llm.payloads[0]["sources"][0]["anchored_on"] == WRITTEN
    assert first["model_calls"] == 1 and first["cached"] == 0
    assert second["model_calls"] == 0 and second["cached"] == 1
    assert second["cached_tokens"] == 100
    assert second["requests"] == first["requests"]
    assert second["requests"][0]["weekdays"] == first["requests"][0]["weekdays"]


def test_a_binding_policy_code_cannot_honour_is_kept_as_such():
    repository = _Repository(_profile(rest_policy="מנוחה של 12 שעות בין משמרות"))
    llm = _Llm(_answer(unresolved=[{"source_id": "source-1", "reason": "מדיניות מנוחה"}]))

    for week in (WEEK, NEXT_WEEK):
        left = _translate(llm, repository, week=week)
        assert left["requests"] == [] and left["unresolved"][0]["reason"] == "מדיניות מנוחה"
    assert len(llm.payloads) == 1
    assert report(repository, TEAM)[0]["status"] == "unresolved"


def test_what_code_refused_is_tried_again_rather_than_kept():
    repository = _Repository(_profile(rules=[RULE]))
    ghost = _avoid(employee="רפאל")
    llm = _Llm(*[_answer([ghost], timing=[_timing()]) for _ in range(4)])

    result = _translate(llm, repository)

    assert result["requests"] == [] and RULE in result["unresolved"][0]["text"]
    assert repository.rows == {}


def test_editing_one_rule_translates_only_that_rule():
    other = "עדיף שיוסי לא יעבוד בבקרים"
    repository = _Repository(_profile(rules=[RULE, other]))
    _translate(_Llm(_answer(
        [_avoid(), _avoid("source-2", "יוסי", weekdays=(), shifts=(MORNING,))],
        timing=[_timing(), _timing("source-2")])), repository)

    repository.profile = _profile(rules=[RULE + " ושלישי", other])
    llm = _Llm(_answer([_avoid(weekdays=("שני", "שלישי"))], timing=[_timing()]))
    result = _translate(llm, repository)

    sent = llm.payloads[0]["sources"]
    assert len(sent) == 1 and RULE + " ושלישי" in sent[0]["text"]
    assert result["cached"] == 1 and len(result["requests"]) == 2


def test_a_roster_change_translates_everything_again():
    repository = _Repository(_profile(rules=[RULE]))
    _translate(_Llm(_answer([_avoid()], timing=[_timing()])), repository)

    repository.profile = _profile(rules=[RULE], employees=("דנה", "דניאל", "יוסי", "עודד"))
    llm = _Llm(_answer([_avoid()], timing=[_timing()]))
    _translate(llm, repository)

    assert len(llm.payloads) == 1


def test_this_builds_instruction_is_never_kept():
    repository = _Repository(_profile())
    answers = [_answer([_avoid()]) for _ in range(2)]
    llm = _Llm(*answers)

    _translate(llm, repository, instructions="דנה לא בלילה של שני")
    _translate(llm, repository, instructions="דנה לא בלילה של שני")

    assert len(llm.payloads) == 2
    assert llm.payloads[0]["sources"][0]["mode"] == "period"
    assert repository.rows == {}


SICK = "חולה 3 או 4 ימים"


def _sick_answer():
    certain = _avoid(employee="עודד", hard=True, dates=("2026-10-20", "2026-10-21", "2026-10-22"),
                     weekdays=(), shifts=(), reason="עודד חולה")
    maybe = _avoid(employee="עודד", dates=("2026-10-23",), weekdays=(), shifts=(), weight=3,
                   reason="עודד אולי עדיין חולה")
    return _answer([certain, maybe], timing=[_timing(
        kind="relative", starts="2026-10-20", ends="2026-10-22", maybe="2026-10-23",
        question="לחסום את עודד גם ב-23.10?")])


def test_sick_for_three_or_four_days_is_dated_from_when_it_was_written():
    repository = _Repository(_profile(notes={"עודד": SICK}))
    llm = _Llm(_sick_answer())

    result = _translate(llm, repository)
    schedule = generate_span(repository.profile, *WEEK, requests=result["requests"])

    working = {row["date"] for row in schedule["assignments"] if row["employee"] == "עודד"}
    assert not working & {"2026-10-20", "2026-10-21", "2026-10-22"}
    line = report(repository, TEAM, today=WRITTEN)[0]
    assert line["status"] == "compiled" and line["expires_on"] == "2026-10-23"
    assert line["question"] == "לחסום את עודד גם ב-23.10?" and not line["expired"]
    assert report(repository, TEAM, today="2026-10-24")[0]["expired"]


def test_compiling_again_counts_from_the_same_day():
    repository = _Repository(_profile(notes={"עודד": SICK}))
    _translate(_Llm(_sick_answer()), repository)

    repository.profile = _profile(notes={"עודד": SICK}, employees=("דנה", "יוסי", "עודד", "רון"))
    llm = _Llm(_sick_answer())
    DirectiveAgent(llm).translate(repository.profile, *WEEK, cache=_cache(repository, "2026-10-27"))

    assert llm.payloads[0]["sources"][0]["anchored_on"] == WRITTEN


def test_a_relative_date_before_it_was_written_is_not_believed():
    repository = _Repository(_profile(notes={"עודד": SICK}))
    early = _avoid(employee="עודד", hard=True, dates=("2026-10-01",), weekdays=(), shifts=())
    llm = _Llm(_answer([early], timing=[_timing(kind="relative", starts="2026-10-01",
                                                 ends="2026-10-01")]))

    assert _translate(llm, repository)["requests"] == []  # A binding note left out.
    row = next(iter(repository.rows.values()))
    assert row["status"] == "unresolved" and row["reason"] == UNREAD_TIME


def test_a_recurring_sentence_spread_over_this_week_is_used_but_not_kept():
    repository = _Repository(_profile(rules=[RULE]))
    spread = _avoid(dates=("2026-10-19",), weekdays=())
    llm = _Llm(_answer([spread], timing=[_timing()]))

    result = _translate(llm, repository)

    assert result["requests"][0]["dates"] == ["2026-10-19"]
    assert repository.rows == {}


def test_an_absolute_date_must_be_written_in_the_sentence():
    repository = _Repository(_profile(notes={"דנה": "בחופשה 3-7.11"}))
    inside = _avoid(hard=True, dates=("2026-11-04",), weekdays=(), shifts=())
    outside = _avoid(hard=True, dates=("2026-11-09",), weekdays=(), shifts=())

    kept = _translate(_Llm(_answer([inside], timing=[_timing(kind="absolute")])), repository)
    assert kept["requests"][0]["dates"] == ["2026-11-04"]

    repository.rows.clear()
    left = _translate(_Llm(_answer([outside], timing=[_timing(kind="absolute")])), repository)
    assert left["requests"] == [] and left["unresolved"]


def test_dates_written_in_a_sentence_are_read():
    anchor = datetime.date(2026, 10, 20)
    assert mentioned_dates("בחופשה 3-7.11", anchor) == [
        datetime.date(2026, 11, 3), datetime.date(2026, 11, 7), datetime.date(2026, 11, 7)]
    assert mentioned_dates("ב-2/1", anchor) == [datetime.date(2027, 1, 2)]
    assert mentioned_dates("2026-12-01", anchor) == [datetime.date(2026, 12, 1)]


def test_saving_setup_queues_one_translation_and_calls_no_model():
    repository = _Repository(_profile())
    service = ProfileService(repository)

    service.update(TEAM, rules=[{"text": RULE, "priority": "soft"}])
    service.update(TEAM, rules=[{"text": RULE, "priority": "soft"}])

    assert [job["kind"] for job in repository.jobs] == ["compile_sources"]


def test_a_structured_recurring_constraint_is_not_sent_to_be_translated():
    structured = {"days": ["שני"], "shifts": [NIGHT], "available": False, "is_hard": True}
    profile = _profile()
    profile["employees"][0]["recurring_constraints"] = [structured]
    repository = _Repository(profile)

    ProfileService(repository).update(TEAM, employees=profile["employees"])

    assert repository.jobs == []


def test_the_worker_translates_setup_so_the_first_build_asks_nothing():
    profile = _profile(rules=[RULE], notes={"עודד": SICK},
                       rest_policy="מנוחה של 12 שעות בין משמרות")
    repository = _Repository(profile)
    sick = _sick_answer()
    answer = _answer(
        [_avoid()] + [dict(row, source_id="source-2") for row in sick["requests"]],
        unresolved=[{"source_id": "source-3", "reason": "מדיניות מנוחה"}],
        timing=[_timing(), dict(sick["timing"][0], source_id="source-2")])
    llm = _Llm(answer)

    kept = SourceCompiler(repository, llm, today=WRITTEN).compile(TEAM)

    assert kept == 3
    assert {line["status"] for line in report(repository, TEAM)} == {"compiled", "unresolved"}
    built = _translate(_Llm(), repository)  # No model call: everything is kept.
    assert [row["source_id"] for row in built["unresolved"]] == ["source-3"]


def test_the_worker_with_no_model_keeps_nothing_and_does_not_fail():
    repository = _Repository(_profile(rules=[RULE]))

    kept = SourceCompiler(repository, _Llm(AgentError("לא הוגדר מודל")), today=WRITTEN).compile(TEAM)

    assert kept == 0 and repository.rows == {}


def test_a_build_from_kept_translations_says_so_and_spends_nothing():
    repository = _Repository(_profile(rules=[RULE]))
    SourceCompiler(repository, _Llm(_answer([_avoid()], timing=[_timing()])),
                   today=WRITTEN).compile(TEAM)

    result = Scheduler(_Llm()).generate_span(
        repository.profile, *WEEK, translation_cache=_cache(repository))

    assert result["metrics"]["engine"] == "hybrid"
    assert result["metrics"]["model_calls"] == 0
    assert result["metrics"]["compiled_hits"] == 1
    assert result["metrics"]["tokens_saved"] == 100
    assert result["metrics"]["total_tokens"] == 0
    assert "תרגום שמור" in result["summary"]


def test_a_null_cache_keeps_nothing():
    llm = _Llm(_answer([_avoid()], timing=[_timing()]), _answer([_avoid()], timing=[_timing()]))
    for _ in range(2):
        DirectiveAgent(llm).translate(_profile(rules=[RULE]), *WEEK, cache=NullCache(WRITTEN))
    assert len(llm.payloads) == 2


def test_the_worker_runs_a_compile_job_and_does_not_report_its_failure():
    from app.worker import JobWorker

    class _Compiler:
        def __init__(self):
            self.teams = []

        def compile(self, team_id):
            self.teams.append(team_id)
            raise RuntimeError("boom")

    class _Jobs:
        def __init__(self):
            self.finished = []

        def finish_copilot_job(self, job_id, error="", retry=False):
            self.finished.append((job_id, retry))

    compiler, jobs = _Compiler(), _Jobs()
    worker = JobWorker(jobs, compiler=compiler)

    worker._process({"id": "j1", "team_id": TEAM, "kind": "compile_sources",
                     "payload": {}, "attempts": 3})

    assert compiler.teams == [TEAM]
    assert jobs.finished == [("j1", False)]
