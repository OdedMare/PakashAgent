# Running many teams at once

How to run the system for 100+ teams, and how to find what is slow when it
is. The reasoning is [D45](DECISIONS.md); this page is the operating guide.

## The shape

```
browser ─► frontend (Next) ─► backend: WEB_CONCURRENCY API processes ─┐
                                worker: python -m app.worker ──────────┼─► PostgreSQL
                                model server (Ollama / hosted) ◄───────┘
```

- **API processes** serve pages. Every route is a sync handler on a
  thread pool, so one process is one CPU's worth of Python. Raise
  `PAKASH_API_WORKERS` (compose → `WEB_CONCURRENCY`) to about the number of
  cores the API container may use.
- **The worker** runs builds, chat turns and translations. Keep it out of
  the API processes (`PAKASH_EMBEDDED_WORKER=false`, as compose does);
  otherwise every API process runs its own six job lanes.
- **The solver is CPU-bound.** On a host shared with PostgreSQL and the
  API, cap it with `PAKASH_SOLVER_CPU_BUDGET` (threads per process) so a
  build cannot take every core while pages wait.

More than one API process needs one session key for all of them:
`PAKASH_SESSION_SECRET`, or the key generated into the database (D39).

## Connections

Every process holds up to `PAKASH_DATABASE_POOL_SIZE` (16) pooled
connections and one `LISTEN` connection; each model call in flight holds
one more. So the database must allow at least:

```
API processes × (pool + 1)  +  worker × (pool + 1)  +  PAKASH_LLM_MAX_CONCURRENCY  +  ~10 for admin
4 × 17 + 17 + 4 + 10 = 99
```

Compose sets `max_connections=200` (`PAKASH_PG_MAX_CONNECTIONS`). Several
backend containers multiply the first term.

**Do not put PgBouncer in transaction mode in front of the app.** The job
claim and the model slots hold session advisory locks, `LISTEN` needs a
session of its own, and `search_path` is set per connection; all of them
break when transactions land on different server connections (D45).

## PostgreSQL settings

Compose passes these to the `db` service; override from `.env`:

| Variable | Default | Guidance |
|---|---|---|
| `PAKASH_PG_MAX_CONNECTIONS` | 200 | The sum above, with room |
| `PAKASH_PG_SHARED_BUFFERS` | 512MB | About ¼ of the database host's RAM |
| `PAKASH_PG_EFFECTIVE_CACHE_SIZE` | 1536MB | About ¾ of its RAM |
| `PAKASH_PG_WORK_MEM` | 16MB | Per sort, per query: keep it modest |
| `PAKASH_PG_LOG_SLOW_MS` | 500 | Statements slower than this are logged |

`max_connections` and `shared_buffers` take effect only on a restart of the
database container.

## Finding the slow query

`pg_stat_statements` is preloaded. Create the extension once (a fresh volume
or an existing one alike):

```bash
docker compose exec db psql -U pakash -d pakash -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements"
```

Then, after the system has carried real traffic for a while:

```bash
docker compose exec db psql -U pakash -d pakash -c "SELECT round(total_exec_time) AS total_ms, calls, round(mean_exec_time::numeric, 2) AS mean_ms, left(query, 120) AS query FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 15"
```

`total_ms` is what to fix first: a cheap query called constantly can cost
more than a slow one called rarely. For the top entries, run the query under
`EXPLAIN (ANALYZE, BUFFERS)` with real ids and look for a `Seq Scan` on a
large table. To start counting afresh after a fix:

```bash
docker compose exec db psql -U pakash -d pakash -c "SELECT pg_stat_statements_reset()"
```

Is the API waiting on its pool rather than on the database? Count
connections per state:

```bash
docker compose exec db psql -U pakash -d pakash -c "SELECT state, count(*) FROM pg_stat_activity WHERE usename = 'pakash' GROUP BY state"
```

Many `active` means the database is the bottleneck: fix queries. Few
`active` and pages still slow, with every pooled connection checked out,
means the API is: add API processes, or raise `PAKASH_DATABASE_POOL_SIZE`
within `max_connections`.

`python -m app.diagnose` inside the backend container prints the job queue
and the model slots.
