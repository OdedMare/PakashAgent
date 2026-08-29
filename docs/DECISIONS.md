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

**⚠️ Superseded in part by [D14](#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10).**
Employees now have identities and may *submit constraint requests*. The
reasoning above still holds where it was actually about blocking — no
submission gates a schedule. Read D14 before acting on this entry.

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

## D11 — The audit was built before anything trusted it *(resolved)*

Workspaces were built ahead of [`BUILD_ORDER.md`](BUILD_ORDER.md) step 3 at the
boss's request. The ordering note held: `bl/audit.py` and its table-driven tests
landed **before** the scheduler and the changes loop, so nothing downstream was
built on top of an audit that did not exist.

*Kept as a record.* The reason it mattered is worth remembering — `audit.py` is
the one module whose correctness everything else assumes, and it is the easiest
thing in the codebase to get exactly right. The importer, still unbuilt, is the
last thing that will lean on it.

---

## D12 — Dragging a shift is a *proposal*, not an edit

The management calendar lets the manager drag an assignment to another slot.
The drop **does not write**. It opens a confirmation that collects the
manager's reason, and only that dialog applies the move.

*Why:* [D3](#d3--the-agent-decides-code-only-audits-) says changes happen by
talking, and [D8](#d8--two-reasons-both-required) requires two reasons on
every change. A drag that wrote directly would satisfy neither — the
`change_log` would gain a row nobody could account for, which is the one
thing the log exists to prevent. Routing the gesture through the same
propose-then-confirm path as a typed sentence keeps the direct-manipulation
feel without reversing either decision. The drag is a faster way to *say what
you want*, not a way around saying why.

The move is stored with the manager's reason and an agent reason that says
plainly that the manager moved it — rather than manufacturing a judgment the
agent did not make.

## D13 — Constraints are recorded by the manager, with their source marked

The management area lets the **manager and the agent** record availability
constraints. Employees still do not enter anything themselves.

`availability.source` is one of `manager`, `agent`, `employee_reported`, or
`interview`. It records **where the information came from, not who typed it**.
`employee_reported` means the manager wrote down what someone told them out
of band.

*Why:* the product wants "the agent can set constraints for employees, and
see the ones they raised themselves". The second half cannot mean employees
writing to the app: [D5](#d5--employees-are-read-only) makes them read-only
and [D10](#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)
gives them no identity at all, so there is nobody to attribute a submission
to and no way to authenticate one. Marking provenance answers the real need —
"Dana said she cannot do Thursdays" is preserved as a distinct fact from "the
manager decided Dana is off Thursdays" — without inventing employee accounts.

If per-employee submission is ever genuinely wanted, that is the point to
revisit D5 and D10 together and give members real identities. Do not bolt an
unauthenticated form onto the share link.

**That happened — see [D14](#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10).**
The condition holds: identities are real, and the submission path is
authenticated rather than bolted onto the share link. `source` keeps the
meaning defined here — an approved employee submission is written as
`employee_reported`.

---

## D14 — Employees get real identities and may submit constraints ⚠️ *(reverses D5, amends D10)*

**This reverses [D5](#d5--employees-are-read-only) and amends [D10](#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link). Both were opened deliberately, together, at the boss's request.**

An employee now has an identity in their workspace and a personal area: their
own hours, their own shifts, their own warnings, and a form that **submits a
constraint for the manager's approval**. [D13](#d13--constraints-are-recorded-by-the-manager-with-their-source-marked)
anticipated exactly this and named the condition — *"if per-employee
submission is ever genuinely wanted, that is the point to revisit D5 and D10
together and give members real identities."* That is what this is. The
condition D13 attached still binds: this is a real identity, **not** an
unauthenticated form bolted onto the share link.

**What is now true:**

- **Employees have identities.** A member claims a name from the workplace
  profile and sets a personal passcode. `employee_identities` maps a claimed
  name to a credential within one team.
- **Employees write, in exactly one way.** They submit *constraint requests*.
  They still do not assign, move, accept, decline, or edit a schedule. The
  write surface is one table, `constraint_requests`, and nothing else.
- **A submission is a request, not a constraint.** It lands as `pending` and
  changes nothing. Only the manager's approval writes an `availability` row
  — with `source='employee_reported'`, which is the value D13 already
  defined for this exact fact.

**What is deliberately unchanged:**

- **The share link still works, still grants read-only.** Claiming a name is
  an *upgrade* on top of it, not a replacement. A team that does not want
  identities keeps the D10 behaviour untouched, and the roster view for an
  unclaimed visitor is what it was.
- **The audit stays advisory.** A pending request is not a constraint and is
  invisible to `audit.py` until approved. Approving one is what makes it
  countable — which keeps [D3](#d3--the-agent-decides-code-only-audits-)
  intact rather than letting a submission silently change the arithmetic.
- **The manager remains the sole decider.** Approval is a manager action, and
  a rejection carries the manager's reason.

*Why the reversal was accepted:* D5's stated cost was that employee consent
as a *finalization gate* lets one unresponsive person hold a schedule
hostage. That reasoning is about **blocking**, and it survives — nothing here
blocks. A pending request does not delay publishing, does not gate a change,
and expires into irrelevance if ignored. What D5 also cost, which was not
priced at the time, is that every constraint had to route through the
manager's memory: "Dana said she cannot do Thursdays" was only in the app if
the manager remembered to type it. That is the failure this fixes.

*Why identity could not be avoided:* "the hours **he** worked" is not
expressible under D10. The share link is one bearer token for the whole team,
so every visitor is indistinguishable from every other — there is no "he" to
filter on. A personal view requires knowing who is looking. This is the
consequence D10 flagged in its own text.

**⚠️ The share link remains a bearer credential.** Claiming a name requires
holding it, so anyone with the link can attempt to claim any *unclaimed*
name. A claimed name is protected by its passcode. Rotating the link does not
release claims — `POST /api/workspace/identity/release` is what a manager
uses when someone leaves.

---

## D15 — The agent speaks first, but still never writes

The agent no longer waits to be addressed. It reads the current state on its
own and **opens the conversation**: when the manager enters the management
area, after anything changes, before a period is published, and periodically
while the room is left open.

What it produces is a **briefing** — a headline, up to four observations, and
for each one a *suggestion*: the sentence the manager could send to act on it.

**A suggestion is text, not an action.** Clicking one types it into the
composer. The manager still sends it, the agent still proposes, and the
manager still confirms with their reason. There is no field in a briefing
that `apply` can read, and `bl/briefing.py` returns exactly three keys —
`headline`, `items`, `quiet` — so there is nothing an operation could hide in.

*Why this shape and not autonomy:* "be proactive" reads like a request for an
agent that acts. Acting would reverse three decisions at once —
[D3](#d3--the-agent-decides-code-only-audits-) (the manager decides what
lands), [D8](#d8--two-reasons-both-required) (every change carries the
manager's reason, which only they can supply), and
[D12](#d12--dragging-a-shift-is-a-proposal-not-an-edit) (even a *drag* is only
a proposal). The gap those protect is not friction, it is the product. What
was actually missing was different: the agent had nothing to say until spoken
to, so noticing anything required the manager to think to ask. Initiating the
conversation fixes that and costs none of it.

**The arithmetic does not move.** `warnings` and `fairness` are computed by
`bl/audit.py` and handed to the model as facts to reason about. It is asked
what the numbers *mean together* — the part code cannot do — and never to
count anything. Speaking first does not change which side of D3 does
arithmetic.

**Silence is a supported answer.** `quiet` is the common case by design, and
it is decided in code from whether there are items rather than taken from the
model's own label. An agent that finds something urgent every time gets tuned
out, and being tuned out is the only real failure mode for something that
speaks unprompted.

**A briefing never fails loudly.** It is decoration on a screen that must
render regardless, so a model that is down or slow returns quiet rather than
an error. `POST /api/schedule/brief` is boss-only, like every other agent
route: a briefing reads drafts, pending requests, and other people's stated
reasons.

---

## D16 — An employee is told what changed, and acknowledging is what marks it read

The personal area leads with **what moved since this person last looked**: a
count, a banner, and the affected rows marked in their own change list.

`employee_identities.acknowledged_at` is what "last looked" means, and it is
deliberately **not** `last_seen_at`. That column advances on every login, so
by the time the personal area renders it is already *now* and nothing could
ever be new against it. `acknowledged_at` moves only when the employee says
they have read what they were shown — `POST /api/employee/acknowledge`.

*Why this was the gap:* the change log already recorded every move and its
reason ([D4](#d4--living-schedule-not-versioned),
[D8](#d8--two-reasons-both-required)), and
[D14](#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10)
already gave each employee a personal view of it. What was missing was the
smallest part: nothing said *this is new*. A manager could move someone's
shift, record the reason, publish, and the person would find out by noticing
a difference in a grid — or not at all. The data was all there; only the mark
was missing.

**A NULL acknowledgement means everything is new, not nothing.** Somebody who
has never opened the screen has by definition not seen the moves that concern
them, and defaulting the other way would swallow precisely the first
notification worth sending.

**It is a mark, not a message.** Nothing is sent anywhere: no email, no push,
no employee contact details. That would need a delivery channel and addresses
the product does not hold, and it is a separate decision from this one. This
is the app telling someone what changed while they are looking at it.

**It changes nothing about who decides.** An acknowledgement is not consent,
not an acceptance, and gates nothing —
[D5](#d5--employees-are-read-only)'s real cost was blocking, and nothing here
blocks. The manager publishes whether or not anyone has read anything.

**It settles only the caller.** The employee comes off the signed session
cookie, exactly as every other personal read does, so one person clearing
their own badge can never clear a colleague's.

---

## D17 — A schedule leaves as a file; a message is something the agent writes

Two different things people meant by "share the schedule", answered
differently on purpose.

**The file is Excel, and its layout is not a preference.** `GET
/api/schedule/export/{id}` serves the period as `.xlsx` laid out shift-major
with dates across the top — the shape of Sample A in
[`FILE_FORMATS.md`](FILE_FORMATS.md). That is the layout
[the importer](BUILD_ORDER.md) is being built to read, so a week can leave,
be edited in Excel, and come back. Inventing a prettier layout would produce
a file this product cannot read, which is a strange thing for the product to
emit.

`bl/export.py` is pure functions over a stored schedule: no model call, no
repository, nothing decided. It re-presents what the manager already
confirmed, which is what makes it safe for this to be the one output nobody
reviews before it is sent.

**The message is the agent's job.** Posting the week to a group chat is
*writing*, and writing in this product is what the agent does — the manager
asks for it in the conversation they are already having, and can ask for a
different one ("רק הסופ״ש", "רק מה שהשתנה"). A fixed template in code would
be a second voice saying the same thing worse, and it would answer only the
one phrasing somebody anticipated.

The change agent returns it as `reply` with **no operations**, because
nothing is changing — and `needs_reason` stays false for the same reason,
since there is no change to explain the reason for.

**Nothing is sent anywhere.** The product has no channel to the team beyond
the share link, holds no employee contact details, and neither half of this
delivers anything. The manager copies the message wherever it goes. Adding a
real delivery channel is a separate decision with its own consequences —
addresses, consent, and a schedule that can reach people who have not opened
the app.

**Export is boss-only.** A member already reads the published roster through
the share link; a file is a copy that leaves the app entirely, and handing
that out is the manager's call. The unaudited schedule is exported
deliberately: warnings are advice to the manager about the roster, not part
of the roster people read.

---

---

## D18 — The boss can place a shift without the agent ⚠️ *(completes D6)*

[D6](#d6--the-boss-can-author-or-generate) has always said the boss may
**author or generate**. Only the generating half was ever built: every path
that put a person on a slot ran through the model, so "author" meant
importing a file that did not exist yet. This is the authoring half.

**What is now true:**

- **A period can be opened empty.** `POST /api/schedule/blank` builds the
  slot grid and stores it as a draft with nobody on it. It calls **no
  model**: `build_slots()` was always pure Python, because which dates fall
  in a period and which shifts run on them is arithmetic.
- **A cell can be filled by hand.** `POST /api/schedule/assign` writes one
  assignment immediately. `POST /api/schedule/unassign` clears one.
- **`assignments.source` records where a row came from** — `agent`,
  `manager`, or `imported`. This is `availability.source`
  ([D13](#d13--constraints-are-recorded-by-the-manager-with-their-source-marked))
  applied to the other table and means the same thing: **where the
  information came from, not who typed it**. It defaults to `agent`, so every
  row written before this decision keeps the meaning it was written with.

**⚠️ Assigning writes immediately; this does not reverse [D12](#d12--dragging-a-shift-is-a-proposal-not-an-edit).**
A drag *moves somebody who is already placed* — it takes a shift away from
one person and hands it to another, and that is a change somebody is owed an
account of, which is what the confirmation dialog collects. Filling an empty
cell takes nothing away from anybody. There is no one for a reason to be owed
to, and requiring one per cell would make authoring a week by hand cost a
dialog per shift — which is the same as not building this at all. Removing
somebody *is* a change in D12's sense, and the UI asks; it is recorded when
given rather than enforced, because a cell cleared seconds after being filled
by mistake is a correction, not a decision.

**D8 is answered, not relaxed.** `assignments.reason` stays `NOT NULL` and
all three enforcement points stay. A hand-placed row carries the manager's
own sentence, or — when they gave none — a plain statement that a person
placed it. That is the same honesty `_moved_from` already applies to a
dragged shift: say what happened rather than manufacture a judgment the agent
never made.

**The audit does not move.** `bl/audit.py` runs on a hand-built week exactly
as it runs on a generated one, and it still only warns
([D3](#d3--the-agent-decides-code-only-audits-)). This is the *cheap* half of
the product — pure arithmetic, no model — so a manually built schedule is
fully checked even though nothing about it was generated.

**The agent is not in this loop, and that is the point.** A model call per
placed cell would make building a week by hand the most expensive thing in
the product, on a deployment whose model is small and rate-limited. The
manual writes are deliberately *quiet*: they skip the briefing that normally
follows a write. The agent catches up on the next ordinary write, on
publish, or when the manager asks — and
[D15](#d15--the-agent-speaks-first-but-still-never-writes) is untouched,
since a briefing was never something a write was required to trigger.

**The interview is still required.** Skipping the agent is not skipping the
profile: without the declared shift vocabulary there is no grid to build, and
inventing one is exactly the hardcoding
[D9](#d9--shift-vocabulary-is-per-workplace) forbids.

**⚠️ Narrowed by [D22](#d22--the-interview-can-be-ended-early-and-the-profile-says-what-it-owes-️-amends-d18):**
the interview may now be *ended early*, and a partial profile is enough to
open the board. What survives unchanged is the sentence above it — a profile
with no shift vocabulary still yields no grid, by hand or otherwise, and D22
says so on screen rather than working around it.

## D19 — The agent answers with tools; asking and changing stay separate

Multi-step questions — *"מי יכול להחליף את יוסי בסופ״ש"*, *"מה חסר לפני
פרסום"* — are answered by the model **choosing named tools**, each of which
is answered in pure Python. `bl/tools.py` holds six read-only operations
(`read_period`, `employee_state`, `coverage_gaps`, `validate_placement`,
`find_replacements`, `publish_readiness`); `bl/planner.py` runs the loop.

**Asking is a different act from requesting a change**, and they are
different endpoints, different response types, and different cards on the
screen. `POST /api/schedule/ask` returns an *answer* and **carries no
operations at all** — the same property a briefing has
([D15](#d15--the-agent-speaks-first-but-still-never-writes)), so there is
nothing an `apply` could read out of one. A question whose answer implies a
change comes back with `needs_confirmation`, and the manager acts on it
through the unchanged propose-then-confirm path.

*Why tools rather than a bigger prompt:* `ChangeAgent` hands the model the
whole period and asks for operations, which works for a single absence and
stops working the moment a question needs four countable things resolved in
order. Each of those is what
[D3](#d3--the-agent-decides-code-only-audits-) already assigns to code —
arithmetic over a roster is what a model gets subtly wrong in a way that
reads exactly like getting it right. Naming the questions moves each one to
the side of the line D3 already drew, rather than drawing a new one.

**The agent may not claim a placement is valid unless a tool said so.** This
is the one genuinely new guarantee. `find_replacements` re-validates every
candidate through `bl/placement.py` and keeps only those that introduce no
warning, so an option offered as a way out of a problem has been checked
against the same arithmetic that would complain about it.

**⚠️ This does not make the audit a gate, and must not be read as one.**
`validate_placement` returns `blocking: False` like everything else, and
`publish_readiness` returns a `ready` flag that is *descriptive* — nothing
branches on it before a publish, and the publish button stays live over
every warning. What changed is that the agent can no longer *assert*
validity it did not check; the manager's authority to overrule the check is
exactly what it was (D1/D3).

## D20 — A simulation is not a proposal

`POST /api/schedule/simulate` answers *"מה יקרה אם…"* with an impact report:
the warnings a change would introduce and resolve, how coverage and hours
would move, and every person affected — including the one a change takes a
shift *away* from. It persists nothing, and `bl/simulate.py` is handed **no
repository**, so that is a property of the wiring rather than a rule
somebody has to remember — the same shape `bl/changes.py` and
`bl/importer.py` already have.

*Why not just use `propose()`:* proposing already audits a hypothetical, but
it does so as a footnote to a change the manager is being asked to accept. A
manager thinking out loud has not asked for a commitment, and answering them
with a confirm button answers a question they did not ask. The two are
deliberately different shapes in the API and visually distinct on screen —
a simulation renders dashed and in its own colour, because a simulation that
looked like a proposal would be one.

**Approving a simulation is an ordinary `apply()` with the manager's
reason.** There is no dedicated endpoint for it and there must not be: a
second write path is precisely how a confirmation step gets routed around
([D8](#d8--two-reasons-both-required),
[D12](#d12--dragging-a-shift-is-a-proposal-not-an-edit)).

## D21 — The agent remembers preferences, and every one of them is visible

`agent_preferences` stores standing operational context in the manager's own
words — *"עדיף לשאול את יוסי לפני רון לסופ״ש"*, *"מאיה מעדיפה בקרים"*.
Scoped to one team like everything else (D10), with `subject` narrowing it to
one employee or shift.

These are **not rules** — rules are the boss's sentences on the profile and
stay natural language ([D2](#d2--rules-stay-natural-language)) — and **not
constraints**, which are what `bl/audit.py` counts. A preference is context
the agent reads before it proposes, and it **never authorises a write**: it
reaches the model as reported speech, and the confirmation step is unchanged
by anything in the table.

**A single decision does not become a standing rule by having been made.** A
preference the agent proposes lands as `suggested` and is inert — `ask()`
reads only `active` rows — until the manager approves it. That is the line
[D14](#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10)
draws between a request and a constraint, applied here.

**Everything stored is listed, editable, and deletable.** There is no hidden
half of this memory, because a stored preference the manager cannot see is a
rule they never agreed to.

## D22 — The interview can be ended early, and the profile says what it owes ⚠️ *(amends D18)*

**This narrows [D18](#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)'s
closing line — "the interview is still required" — at the boss's request.**

The manager may close the intro interview at any point. Whatever has been
collected is written as the profile, and the management area opens on it. The
interview is no longer a room with one exit that only the agent can open.

*Why:* The interview is roughly twenty topics, and the manager who most needs
this product is the one who does not have an uninterrupted hour for it. The
old shape had `_is_ready` as the only door: the agent declared the profile
finished, or nobody left. On a first interview `onDone` was deliberately
withheld so nobody could reach the board with nothing to schedule against —
which meant a manager out of time had to abandon the *app*, not just the
conversation. That is a worse failure than an incomplete profile, and it was
the common one.

**The readiness gate is untouched.** `_is_ready` still governs what the
*model* may declare finished, and still refuses a profile owing a required
field. Ending is a separate door that only a person can open — an agent able
to reach it would be deciding it had asked enough, which is exactly the
judgement the confirmation turn exists to keep with the manager. Two doors,
one for each party, is the whole shape of this decision.

**Ending costs no model call.** It writes the draft already on the session.
An escape hatch from an interview that has become slow or expensive cannot
itself depend on the model that made it so.

**A partial profile records its own gaps.** `completeness` carries
`missing_topics` (what the scheduler cannot run without) and `open_points`
(what the agent flagged as unsettled). Its *absence* means the interview was
confirmed the ordinary way, so nothing had to be backfilled onto profiles
that already existed.

**The gaps are readable by the agent, through a tool.** `profile_gaps` is the
seventh entry in `bl/tools.py` — pure Python, read-only, in the menu beside
`publish_readiness`, which answers the same shape of question about a period
([D19](#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
So *"מה אתה עוד לא יודע"* is answered from the record rather than from the
model's impression of the conversation. **Naming a gap does not fill it:**
the interview remains the only thing that writes a profile, and the tool can
only point back at it.

**One gap genuinely blocks, and it is not a policy choice.** With no shift
vocabulary there is no grid — not even a hand-built one — because the rows of
the board *are* the workplace's shifts and inventing them is what
[D9](#d9--shift-vocabulary-is-per-workplace) forbids. The board says so
plainly instead of rendering empty. Every other gap degrades the result
rather than preventing it, which is why they are different sentences on
screen rather than one warning.

**D3 is untouched, and this is the reason the rest holds.** Nothing here
blocks: the board opens, the scheduler runs on a thin profile and returns a
thin schedule, and the audit warns exactly as it always did
([D3](#d3--the-agent-decides-code-only-audits-)). The gaps are *reported*.
A partial profile that refused to schedule would be the audit becoming a
gate, arriving through a side door.

**Where the refusal lives, and why it is not that gate.** The one blocking
gap is checked in `schedule_service._buildable_profile`, which both
`generate` and `create_blank` call. It refuses on *absent shift vocabulary
only* — never on missing rules, employees, or open points, which still
produce a thin schedule exactly as the paragraph above requires. This is not
the audit becoming a gate: the audit reports on a grid that exists, and this
says there is no grid to report on. The test is the one `build_slots` itself
applies, so the gate and the builder cannot disagree — when they did, the
profile passed a looser check, the builder returned no rows, and both
buttons answered `502` with nothing the manager could act on. That was the
board *not* saying so plainly, which is what this decision asked for.

The refusal is a `ProfileIncompleteError` carrying the `completeness` lines,
so the client can open the interview on exactly what is owed or take the
question to the agent first. **It still writes nothing and fills no gap**
(D19): the interview remains the only thing that writes a profile.

## D23 — The copilot is durable, permissioned, and reversible

The proactive agent now runs in a separate backend process. PostgreSQL owns
its queue: jobs are deduplicated, claimed with row locking, retried, and
recovered when a worker dies. Closing the browser therefore stops neither the
observation loop nor its record of what happened.

**The inbox is the action boundary.** A scan may create an observation, a
proposal, or a failure. It cannot smuggle an operation into a briefing. The
manager sees every item, its evidence, its status and the verification result
in one place. Repeated findings have stable fingerprints, so an always-awake
agent does not become an always-nagging one.

**Permission is per action type:** `observe`, `suggest`, or `auto`. Automatic
follow-up may open a resumable interview, because opening a question answers
nothing and writes no workplace fact. Automatic schedule repair still stops
at a proposal: [D8](#d8--two-reasons-both-required) requires a manager's own
reason before any assignment changes, and a permission switch cannot invent
one.

**Follow-up interviews start from the current profile.** The copilot notices a
recorded gap or a profile older than ninety days and opens one focused
conversation. It never answers the question itself, and it does not make the
manager rebuild the workplace from an empty draft.

**Audit is append-only.** Creation, approval, dismissal, permission change,
verification and rollback each add an event. Rollback adds history; it never
deletes history. An untouched follow-up session can be removed safely. Once a
person has answered it, rollback is refused because deleting their answer
would be data loss. Schedule repair proposals remain on the ordinary
propose-confirm path and therefore never need rollback before confirmation.

## D24 — The agent asks when it would otherwise guess ⚠️ *(strengthens D8)*

A request the agent cannot carry out without guessing **which person, shift,
date, team, rotation or assignment** it refers to is answered with **one
focused question**, and nothing is proposed behind it.

**The threshold differs by what the request would do**, and that asymmetry is
the decision:

- **Reading** (`bl/planner.py`) may interpret. A question answered against a
  reasonable reading of a loose sentence costs a re-ask and moves nothing, so
  it asks only when a guess would change *what it reports*.
- **Writing** (`bl/changes.py`) may not. A change applied to the wrong
  person's shift has to be *found* before it can be undone, and the manager
  who would find it is the one who trusted the proposal.

**On the write path this is enforced in code, not by the prompt.**
`_unresolved_people` checks every name an operation carries against
`tools.resolve_employee`; a name matching nobody, or several people, empties
the proposal and turns it into a question — the same treatment
[D8](#d8--two-reasons-both-required)'s missing reason already gets, for the
same reason. A model that forgets the rule once must not be able to move
somebody. `resolve_employee` returns *several* matches rather than the first,
because picking the first is precisely the guess being refused.

**Two gates, one question at a time.** `needs_reason` is a missing *why*;
`needs_input` is a missing *what*. Either holds a proposal, and the target is
settled before the reason is collected: a reason recorded against the wrong
person is worse than a missing one, and a manager handed two questions
answers neither.

**A clarification continues the request rather than replacing it.**
`pending_request` travels out with the question and back with the answer, and
the two are read as one sentence — the manager answers *"ערב"*, never
*"תשבץ את דניאל במשמרת ערב"*. It is plain text, deliberately not a parsed
pending-intent record: the sentence is what the model already reads, and a
structured duplicate is a second thing to keep in sync. It is cleared the
moment the request is carried out, so an answered question cannot be reopened
by a stale echo, and both agents are shown what they already asked
(`asked_last_turn`) so the same question is never put twice.

*Why the client carries it:* the alternative is per-manager conversation
state on a stateless route. `pending_request` is content, not authority — it
reaches the model as part of the sentence, names no schedule and selects no
row, so `team_id` from the signed cookie remains the only thing that scopes a
write ([D10](#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).

**⚠️ This is not the audit becoming a gate.** Nothing here refuses a change
the manager wants; it refuses one the *agent* would have aimed by guessing.
Once the target is named, the placement proceeds over every warning exactly
as before ([D3](#d3--the-agent-decides-code-only-audits-)).

**A tool failure is not an ambiguous request.** Nothing matching found, a
technical error, and "which of these did you mean" are three different
answers. The deterministic fallback still answers the question rather than
asking what the manager meant — an unreachable model is not the manager
having been unclear, and asking would repeat on every retry.

## Open

- **Python version.** PakashAgent uses **Python 3.11**. It originally mirrored
  AiSummryIO's EOL 3.8.10 runtime, then moved to 3.11 so the official OpenAI
  Agents SDK could own agent/tool execution.
