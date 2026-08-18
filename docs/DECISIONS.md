# Design decisions

Settled in a design interview with the boss (the product owner). Each entry
records the decision **and why**, because several are counterintuitive and one is
a deliberate tradeoff that looks like a bug if you find it cold.

Read this before changing architecture. If you disagree with one, the reasoning
is here to argue against — don't silently reverse it.

---

## D1 — Rules are hard or soft

Hard rules must hold. Soft rules are optimized toward. The intro interview tags
each rule as it collects it.

## D2 — Rules stay natural language

There is **no structured rule vocabulary**, no rule-type enum, no rule builder
UI. The boss's own sentences are kept and passed to the model as context.

*Why:* This was originally going to be a typed rule engine. D3 removed the need —
if code isn't enforcing rules, code doesn't need to represent them. Follows from
D3; don't reintroduce structured rules without revisiting that.

## D3 — The agent decides; code only audits ⚠️

**The most important decision here.**

The agent makes every scheduling decision and explains it in natural language.
A pure-Python checker (`bl/audit.py`) recomputes the *countable* facts — hours per
person, consecutive shifts, double-booking, availability conflicts, unfilled
slots — and returns **warnings**.

The audit **never blocks, never rewrites, never rejects**. It reports.

*Why:* The boss wanted a "pure agent" product, not a constraint solver wearing a
chat interface. The audit exists because arithmetic over a roster is the one
thing an LLM reliably gets subtly wrong, and a wrong answer there looks exactly
like a right one — a confident schedule with someone on their 6th shift. Nothing
throws; a person just doesn't show up. So code checks the arithmetic, and the
agent keeps the judgment.

**⚠️ Accepted tension with D1:** D1 calls hard rules inviolable, but the audit is
advisory. So "hard" means *a strong instruction to the model plus a loud warning
when broken* — **not a gate**. The boss was told this explicitly and chose it.
Do not "fix" it by making the audit blocking.

## D4 — Living schedule, not versioned

One current schedule per period, edited in place, plus an **append-only change
log** (what changed, the boss's reason, when).

*Why:* The real questions are "who works tonight" and "why did Yossi get moved."
Neither needs snapshots. Full versioning — version tables, diff UI, rollback
semantics — is real work for a need that hasn't appeared. The change log answers
the second question and is where D8's reason is stored.

## D5 — Employees are read-only

The boss is the sole actor. Employees view the schedule; they do not sign, accept,
decline, or submit availability through the app.

*Why:* Considered and rejected: employee consent as a finalization gate. It lets
one unresponsive person hold a schedule hostage and needs deadlines, escalation,
and boss override — contradicting "only the boss confirms."

## D6 — The boss can author *or* generate

Both. The boss may hand over a finished schedule (typically an import) or ask the
agent to build one. Both paths produce the same representation.

*Why:* This is why import is a first-class path rather than a convenience. The
agent must be able to reason about a schedule it did not author.

## D7 — Import infers layout, boss confirms

No fixed template. The agent reads whatever it's given, infers the structure, and
shows its interpretation for confirmation before committing anything.

*Why:* A template fails on the first file that predates the app — which is
exactly the "past shifts" case. See [`FILE_FORMATS.md`](FILE_FORMATS.md); the two
real samples are structurally different from each other, which settles it.

## D8 — Two reasons, both required

- **The boss's reason** — why the change is happening ("sick", "vacation"). The
  agent asks if it wasn't volunteered. Recorded in the change log against the
  employee.
- **The agent's reason** — why it chose this replacement. Shown at confirmation
  time.

*Why:* Different jobs. The boss's reason is a record that can't be reconstructed
later — it's what makes "how many sick days has Dana taken" answerable. The
agent's reason is a check *before* the change lands: under D3 the agent's judgment
is final, so seeing "I picked Yossi because he's at 22 hours and Ron is at 31" is
the boss's chance to catch a bad call cheaply.

## D9 — Shift vocabulary is per-workplace

Shift names are **not hardcoded**. The intro interview collects them: the names,
their times, and whether any are on-call.

*Why:* The two real sample files already disagree — one has 2 shifts
(בוקר/צהריים), the other has 3 (בוקר/צהריים/כונן לילה). Hardcoding would mean
shipping a guessed union. Matching sheet headers against a vocabulary the boss
declared is both more correct and easier than open-ended inference.

**Note:** `כונן לילה` is *on-call* night, not a regular night shift. The interview
must ask how on-call counts toward hours and fairness, because `audit.py` needs to
weight it.

---

## D10 — One workspace per team; the boss holds a password, members hold a link

Each team gets a separate workspace. Every row that belongs to a workplace
carries `team_id`, and every read filters on it.

The two sides authenticate differently, on purpose:

- **The boss** picks a password when the workspace is created. It is what
  authorizes authoring — the interview, the settings, and later the schedule.
- **Members** get an unguessable share link (`/team/<token>`) and no account at
  all. Following it grants a read-only session.

*Why the asymmetry:* it falls out of [D5](#d5--employees-are-read-only). Members
never write, so they never need an identity — only proof they were invited.
Giving them accounts would mean signup, password reset, and invitations by
email: a large amount of machinery in service of a side of the product that,
by decision, does nothing but read.

*Consequences worth knowing:*

- **A share link is a bearer credential.** Anyone holding it sees the roster.
  Rotation (`POST /api/workspace/member-link/rotate`) is the only revocation,
  and it revokes for *everyone* — that is what leaves the team.
- **There is no per-member identity**, so "who looked at the schedule" is not
  answerable and "Dana's personal view" is not expressible. If either is ever
  wanted, that is the point to revisit this and give members real accounts.
- **Settings stay process-wide**, not per-team: they hold the database
  credentials and the model key. They are guarded as boss-only, but one
  workspace's boss editing them still moves the ground under every other
  workspace. Per-team model settings would mean making the runtime store
  per-team, which has not been done.
- **`session_secret` must be set in a real deployment.** Unset, each worker
  generates its own and rejects the others' cookies.

## D11 — The audit is still the next thing to build

Workspaces were built ahead of [`BUILD_ORDER.md`](BUILD_ORDER.md) step 3 at the
boss's request. Nothing about them depends on the audit, and nothing downstream
was built on top of the gap — but the ordering note in BUILD_ORDER still holds:
`bl/audit.py` comes before the scheduler, the importer, and the changes loop.

---

## Open

- **Python version.** `AiSummryIO` pins **3.8.10** (EOL), likely a deployment
  constraint there. Mirroring it unless PakashAgent targets a newer environment —
  the boss hasn't answered. If 3.8.10 holds: no `X | Y`, no `list[str]`, no
  `match`; use `Optional`, `List`, `Dict`.
