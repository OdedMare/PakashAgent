# Build order

**Start here in a new session.**

Done so far: step 1 (scaffold and port), step 2 (all tables and their
repositories), **step 3 (`bl/audit.py` and its table-driven tests)**, step 4
(the intro interview, wired through HTTP to an RTL chat UI), step 5
(`bl/scheduler.py`), step 7 (`bl/changes.py` and the change log), and the
management slice of step 8 — the calendar, the agent chat, the roster and
constraints panel, and the read-only member view.

Also done, out of order and at the boss's request: **workspaces** — the `teams`
table, boss login, member share links, and the route guards
([D10](DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).
Nothing downstream depends on it and it does not change the order below.
**Each new table still arrives with its own `team_id`** — added at creation
time, never retrofitted onto a populated table.

Also done, likewise out of order, four features the boss asked for directly:

- the **proactive agent** — `bl/briefing.py` and `Management/Briefing.tsx`,
  where the agent opens the conversation instead of waiting to be asked
  ([D15](DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes));
- **change notifications for employees** — the personal area leads with what
  moved since they last looked, marked by `employee_identities.acknowledged_at`
  ([D16](DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read));
- **export** — `bl/export.py`, a period out as `.xlsx`
  ([D17](DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes));
- **the manual path** — a period opened empty and filled in by hand, with
  `assignments.source` recording where each row came from
  ([D18](DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
  It adds one guarded column and no table, and it is the only
  schedule-building path with no model call on it at all.

None of them adds a table beyond one guarded column, and none changes the
order below. **`export.py` is worth reading before step 6:** it already
writes the Sample A layout the importer must parse, so the two are the same
shape seen from opposite ends.

**Step 6, the importer, is now built** — `bl/importer.py` (layout inference)
and `bl/learn.py` (what a stack of past files says about the workplace), with
both `FILE_FORMATS.md` samples as fixtures under `tests/fixtures/build.py`.
One inference reads both, which is the regression the two samples exist for.

**All eight steps are done.** What remains on the importer is the frontend
confirm screen: `POST /api/schedule/import/preview` returns the
interpretation and writes nothing, and `POST /api/schedule/import/confirm`
is the only endpoint that persists — the D7 split is already enforced at the
HTTP boundary, so the screen has a contract to build against.

Worth knowing about the audit, since everything trusts it: `audit()` takes the
schedule's **slot grid** as well as the assignments. A slot with nobody on it
leaves no row among the assignments, so an audit walking only those reports
nothing for an entirely unstaffed shift — the case the manager most needs
told about. Callers with a stored schedule pass `slots`.

Read first: [`DECISIONS.md`](DECISIONS.md) (the reasoning behind the architecture,
including one deliberate tradeoff that looks like a bug), then
[`../backend/CLAUDE.md`](../backend/CLAUDE.md).

## Resolve before writing much code

**Python version — decided: stay on 3.8.10.** The boss chose to mirror
AiSummryIO's target, so no `X | Y`, no `list[str]`, no `match`; use `Optional`,
`List`, `Dict`. `backend/Dockerfile` builds on `python:3.8.10-slim` to match.

*Caveat worth knowing:* the local `backend/.venv` runs 3.13, so the test suite
passing there does not prove 3.8 compatibility. `vermin -t=3.8 app/` checks the
syntax; `docker build ./backend` is what proves the pinned dependencies actually
resolve. Both pass today, and every module imports under 3.8.10 in the image.

The pin is not free, and `backend/Dockerfile` is where the bill lands: the
3.8.10 image is Debian buster, which is past EOL, so apt has to be pointed at
`archive.debian.org`, and `pydantic-settings` pulls `backports.zoneinfo`, which
has no aarch64 wheel for 3.8 and needs `gcc` to compile. None of that is wrong,
but it is all sunk cost if the deployment target turns out to be newer — worth
re-asking the boss once before more code depends on it.

## Steps

**1. Scaffold and port.**
`pyproject.toml` from AiSummryIO's deps minus `flunks`, plus `openpyxl`. Keep the
`[tool.setuptools.package-data]` block — prompts are markdown and must ship in the
wheel or every LLM call fails with "prompt not found". Port `dal/llm/` wholesale,
plus `common/config`, `common/runtime_settings`, `bl/prompts/_loader.py`,
`dal/repository/base.py`, `dal/database/postgres.py`, `logging_setup`, `errors`.
Rename the env prefix to `PAKASH_`.

**2. Schema and repositories.**
Tables per [`../backend/app/dal/CLAUDE.md`](../backend/app/dal/CLAUDE.md).
`change_log` append-only; `assignments` carries the agent's reason.

**3. `bl/audit.py` + its tests.** ← *do this before the agent work*
Pure functions, no LLM. Table-driven tests: roster + assignments → expected
warnings. Covers over-hours, consecutive shifts, double-booking, unavailability
conflicts, unfilled slots. It is the easiest thing in the codebase to get exactly
right, and everything downstream trusts it.

**4. Intro interview.**
One question per turn with a recommendation. Must collect the **shift vocabulary**
including on-call weighting — the importer and the audit both depend on it.

**5. Schedule generation.**
Assignments carry reasons. Same representation as imported schedules.

**6. Importer.** *(done)*
Both fixtures from [`FILE_FORMATS.md`](FILE_FORMATS.md) are built in
`tests/fixtures/build.py` and one inference passes both — they are
structurally different on purpose, and that is the whole test.

`bl/importer.py` infers axis semantics (which axis is time, whether shift is
nested under date, whether the lanes are shifts or people) with **no model
call**: it is grid arithmetic, and code that counts cannot hallucinate a
person into a shift. `bl/learn.py` is the layer above it — `observe()`
counts patterns across every uploaded file, and `RuleLearner` turns those
counts into candidate rules in the manager's own words (D2), each carrying
the evidence behind it and none of them approved by being proposed (D7).

**7. Conversational changes.**
Ask for the reason, propose with justification, apply on confirm, append to log.

**8. Frontend.**
RTL shell, chat, schedule grid, non-blocking warning banners, import-confirm
screen, read-only employee view.

## Verification

```bash
cd backend && python -m pytest -q     # audit + importer fixtures + prompt loader
docker compose up                      # backend, frontend, postgres, nginx
```

End-to-end against a local Ollama:

1. Run the intro interview; confirm the shift vocabulary is stored.
2. Generate a week; check each assignment carries a reason.
3. Deliberately break a rule; confirm a warning appears **and the schedule still
   renders** — a blocked save means D3 was reversed.
4. Import a sample sheet; confirm the interpretation screen appears and nothing
   persists until approved.
5. Say "Dana's sick Thursday"; confirm the agent asks for a reason, justifies its
   replacement, and both reasons land in the change log.
