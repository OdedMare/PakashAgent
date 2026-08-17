# Build order

**Start here in a new session.**

Done so far: step 1 (scaffold and port), the interview half of step 2 (the
`interview_sessions` / `interview_turns` tables and their repository), step 4
(the intro interview, now wired through HTTP to an RTL chat UI), and the
interview slice of step 8.

**Next: step 3, `bl/audit.py`.** It was deliberately skipped to get the interview
demonstrable, but nothing downstream should be built on top of an audit that
does not exist yet.

Read first: [`DECISIONS.md`](DECISIONS.md) (the reasoning behind the architecture,
including one deliberate tradeoff that looks like a bug), then
[`../backend/CLAUDE.md`](../backend/CLAUDE.md).

## Resolve before writing much code

**Python version.** The plan mirrors AiSummryIO's **3.8.10**, which is EOL and was
probably a constraint of *their* deployment target, not ours. Ask the boss whether
PakashAgent deploys to that same environment. If yes, keep 3.8.10 and avoid
`X | Y`, `list[str]`, and `match`. If no, use 3.11+ — it costs nothing now and
gets more expensive later.

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

**6. Importer.**
Build the two fixtures from [`FILE_FORMATS.md`](FILE_FORMATS.md) *first*, then make
inference pass both. They are structurally different on purpose — that is the
whole test.

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
