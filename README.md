# PakashAgent

An agent that builds and maintains work shift schedules through conversation.

The boss teaches the agent the workplace once, in an intro interview. After that
the agent builds schedules, absorbs schedules the boss already has (Excel or
docs), and rearranges them on request — always explaining what it did and why.
Employees see the result; they do not edit it.

**Hebrew, right-to-left.** Not just the UI — shift names, weekdays, availability
markers, and errors are all Hebrew. See [`backend/app/bl/CLAUDE.md`](backend/app/bl/CLAUDE.md).

## Status

**Design complete, implementation not started.** Every architectural decision was
settled in a design interview and is recorded — with its reasoning — in
[`docs/DECISIONS.md`](docs/DECISIONS.md). Read that before writing code; several
decisions are counterintuitive and one is a deliberate, accepted tradeoff.

The next session should start at [`docs/BUILD_ORDER.md`](docs/BUILD_ORDER.md).

## The four steps the product exists to serve

1. **Intro interview** — the agent asks about the job, the employees, the shift
   structure, dependencies, and the mission. This is where the workplace's own
   shift vocabulary is collected (every workplace names shifts differently).
2. **The boss loads shifts** — or asks the agent to generate them. Both are
   supported and land in the same representation.
3. **Import from Excel/docs** — real files vary structurally. The agent infers
   the layout and shows its reading for confirmation before committing.
4. **Conversational changes** — "Dana's sick Thursday." The agent asks why if the
   boss didn't say, proposes a replacement with its reasoning, and applies it on
   confirmation.

## Architecture at a glance

```
backend/          FastAPI + Postgres, layered api / bl / dal
  app/api/        HTTP contracts and routers
  app/bl/         Decisions: interview, scheduling, changes, audit, import
  app/dal/        Data access: Postgres, LLM client
  app/common/     Config, runtime settings, logging, errors
frontend/         Next.js, RTL, chat-first with a schedule grid
```

Ported from [OdedMare/AiSummryIO](https://github.com/OdedMare/AiSummryIO): the
whole `dal/llm` package (an OpenAI-compatible JSON client that also works against
Ollama, vLLM, and Groq), settings, runtime settings, the markdown prompt loader,
and the repository base. See [`backend/CLAUDE.md`](backend/CLAUDE.md).

## Running it

```bash
docker compose up          # backend, frontend, postgres, nginx
```

```bash
cd backend
python -m pytest -q        # audit.py and the importer fixtures
uvicorn app.main:app --reload
```

The model defaults to a local Ollama endpoint; set `PAKASH_LLM_BASE_URL` and
`PAKASH_LLM_MODEL` to point elsewhere. Nothing here is OpenAI-specific.
