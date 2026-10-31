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

## D3 — The agent decides; code only audits ⚠️ *(amended by D31; assignment superseded by D34)*

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

> **Revived by [D42](#d42--import-is-back-a-sheets-shape-is-data-found-by-code-the-model-or-the-manager-revives-d7).**
> Importing was removed for a while and is back, with the layout as data
> rather than a reader per shape. What is below still holds: no template,
> and nothing is stored before the manager confirms.

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
  *(Amended by [D28](#d28--teams-are-opened-by-צוות-משמרות-זהב-not-by-whoever-reaches-the-login-page-️-amends-d10):
  the operator, צוות משמרות זהב, now opens the workspace and sets the first
  password; the boss can change it from then on.)*
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

*Why:* [D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34) says changes happen by
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
  countable — which keeps [D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34)
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

> **Removed.** The automatic briefings (`bl/briefing.py`,
> `Management/Briefing.tsx`) and the `/brief` route are gone; the agent
> speaks only in the manager chat, when spoken to. Kept as the record of
> what was decided at the time.

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
[D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34) (the manager decides what
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
([D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34)). This is the *cheap* half of
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
[D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34) already assigns to code —
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
([D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34)). The gaps are *reported*.
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

> **Partly withdrawn.** The copilot itself — its scans, inbox, permissions
> and audit — was removed: its approve and rollback changed only a status,
> and everything it noticed the board and the chat already say. What stays
> is the durable queue below, which carries builds, chat turns and
> translations.

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
as before ([D3](#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34)).

**A tool failure is not an ambiguous request.** Nothing matching found, a
technical error, and "which of these did you mean" are three different
answers. The deterministic fallback still answers the question rather than
asking what the manager meant — an unreachable model is not the manager
having been unclear, and asking would repeat on every retry.

---

## D25 — The front door has a worker entrance, but it only signs in *(amends D14)*

The front page asks for the team first, then offers two doors: **מנהל**
(the team password, unchanged from D10) and **עובד/ת** (a claimed name and its
personal passcode, D14). Before this, a worker could only arrive through the
share link, even to sign in to a name they had claimed months ago.

**The worker door signs in; it does not claim.** `POST /api/employee/signin`
takes `team_id` in the body, because there is no session to take it from, and
reaches only a name that is already claimed. Claiming stays behind the
share-link session exactly as D14 set it.

*Why sign-in can drop the link and claiming cannot:* for an existing claim the
passcode is the credential, so the link proves nothing extra. For an
unclaimed name the link is the *only* proof of having been invited. The team
picker on the front page is public, so letting it reach `claim` would let
anyone who can see a team's name take any name its roster has not claimed yet.

*Why the name is typed, not picked:* a picker on a public page would publish
every team's roster to anyone who opens the site. The share-link
`IdentityGate` still lists names, because a visitor there has proven they
were invited.

**Consequences worth knowing:**

- **`/signin` and `/login` share one throttle key**
  (`employee:<team>:<name>`), so two doors to one passcode do not double
  the guesses an attacker gets.
- **A wrong passcode and an unclaimed name answer identically**, as `/login`
  already did. Here that matters more, because this door needs no link.
- **Taking `team_id` from the body is a login's exception to the
  team-from-cookie rule**, the same one `/api/workspace/login` already
  makes: the route issues the cookie, so there is no cookie yet to read the
  team from. Every route *after* sign-in still scopes by the signed session.

## D26 — One manager conversation follows clear instructions *(amends D8 for manager chat)*

The manager chat is the single conversational entry point for scheduling,
employees, availability, recurring constraints, workplace rules and advice.
A clear instruction needs no separate justification. When the manager does not
provide a reason, the chat records their actual request as the audit reason;
the agent still explains its choices separately and must not invent a motive.
Legacy change routes and manual board actions keep their existing contracts.

Advice and “what if” questions produce answers, without a pending mutation.
The chat can run the existing pure-Python simulator over a complete combination
of changes and compare coverage, workload and warnings before recommending it.

Unknown targets, duplicate assignments and malformed operations are repaired
or clarified. Newly introduced rule conflicts are returned to the agent for
one advisory review; it can repair its own choices or describe a deliberate
exception. Existing unrelated gaps do not hold an otherwise valid change.
Recurring rules validate their weekday/shift lists and availability flag before
saving, so unknown fields cannot silently widen a Tuesday constraint to every
day. New employee rows explicitly carry role, eligibility, service and rotation;
omitted fields on existing roster/shift rows preserve their saved values.
Final previews retain explicit Apply approval, exception approval, private
manager history, stale-state checks and atomic writes. A message alone never
writes to the schedule.

## D27 — Employees ask about swaps; the charts are the manager's *(amends D14)*

> **Update:** the employee chat ("שאלו על החלפות", `POST /api/employee/assistant`)
> has since been removed. Employees offer swaps only through the swap form
> under "בקשות והחלפות". The rest of this decision — charts are the
> manager's, `fairness` stays off `/api/employee/me` — still holds.

The personal area's "הנתונים שלי" tab — hours, shift mix and a comparison
against every colleague — is gone. Hours per person is the manager's view
(the stats panel on the board), and `/api/employee/me` no longer carries
`fairness`, so colleagues' hours do not reach an employee's browser at all.
In its place is **"שאלו על החלפות"**: a small chat where an employee asks who
they could swap with, or how their week could work better.

**It suggests; it never writes.** `POST /api/employee/assistant` returns
`answer` and `suggestions` and nothing an `apply` could read — the D15/D19
shape. A suggestion carries a button that sends the **ordinary swap offer**
(`POST /api/employee/swaps`), which still needs the colleague's agreement and
then the manager's decision (D14). There is no new write path.

**Which swaps exist is decided in code.** `bl/employee_service/swap_options.py`
tries the employee's upcoming published shifts against colleagues' and keeps
only trades that introduce **no** audit warning anywhere in the period; ones
that clear a warning about the employee rank first. The model picks from that
list by id and phrases the answer; an unknown id is dropped. This is D19's
"never claim a placement is valid unless a tool said so", applied to the
employee side.

**What the model sees is what the employee's own screen shows** — their shifts,
who is on them with them, their hours, the team *average*, their own warnings —
plus the clean swaps. Colleagues' constraints are read in code to rule swaps
out and never leave it: an option is either offered or absent, with no reason.
Drafts, pending requests and the change log are not read at all.

*Why not reuse the manager chat:* that conversation reads drafts, other
people's stated reasons and pending requests, and prepares plans for approval.
None of that belongs in front of an employee, and a soldier asking "with whom
can I swap Tuesday" needs one answer and a button, not a planning surface.
The conversation lives in the browser only; nothing is stored server-side.

**It answers without a model**, listing the clean swaps (narrowed to a weekday
named in the question), and reports `used_model: false`.

## D28 — Teams are opened by צוות משמרות זהב, not by whoever reaches the login page ⚠️ *(amends D10)*

Before this, anyone who could load the front page could press "פתיחת צוות
חדש", pick a name and a password, and become the boss of a new workspace.
D10 said exactly that — *"the boss picks a password when the workspace is
created"* — and the settings router already admitted the cost in its own
docstring: *"anyone can open a workspace and become its boss."* The boss asked
for that door to close, and for one place to control the whole system.

**What is now true:**

- **The operator is צוות משמרות זהב**, with its own console at `/admin` and
  its own HttpOnly cookie (`pakash_admin`, 12 hours). Not a fourth role on the
  team cookie: an operator belongs to no team, and the two sessions must
  coexist in one browser. Each cookie's reader refuses the other's role.
- **Its password defaults to the settings password** (`010802` unless
  `PAKASH_SETTINGS_PASSWORD` says otherwise). The operator is the one person
  who already held that; `PAKASH_ADMIN_PASSWORD` gives the console a separate
  credential. Both empty keeps the console locked.
- **`POST /api/workspace` answers 403** unless `PAKASH_OPEN_SIGNUP=true`. The
  login page no longer offers to open a team; it says who does.
- **The operator opens a team with a name and a password, nothing more.**
  The first manager password is shown once on a hand-over card, then only its
  hash exists. Afterwards the operator can rename the team, keep a private
  note on it, reset the manager password, rotate the share link, release a
  claimed name, **suspend** and **delete** — and sees every team's numbers:
  employees, claimed identities, periods, pending requests, last activity.
- **How many employees a team has is the manager's decision.** The console
  reports the count (a departed employee is listed, not counted) and never
  limits it. A per-team seat cap was built and removed the same day at the
  boss's direction: the operator opens the door, the manager runs the room.
- **A suspended team is refused at every door and under every open session.**
  `Guards.visitor()` asks the database whether the team is active (cached ten
  seconds per process, cleared at once by the console), because a signed
  cookie outlives a suspension by up to thirty days otherwise. The same check
  makes a *deleted* team's cookies stop working instead of failing deeper.
  The team's data is untouched; resuming restores access exactly.
- **Deleting is `DELETE FROM teams`** and every team table cascades — the
  schedules, the change log, identities, requests, chats, the interview.
  It asks for the team's name typed back, and suspension is offered first as
  the reversible version.
- **The operator reaches `/api/settings` on its own session**, without the
  `X-Settings-Password` header. The console's "מערכת" tab is where the
  process-wide settings now live; a boss can still open them the old way.

**What is deliberately unchanged:**

- **The boss still holds the team password and can change it**
  (`/api/workspace/password`). The operator sets the first one and can reset a
  forgotten one, but does not keep knowing it.
- **Every team route still scopes by the team on the signed cookie.** The
  console's queries are the one deliberate exception — cross-team by design —
  and they live in one mixin, `dal/repository/admin.py`, so the exception is
  a single file to review. None returns a password or passcode hash.

*Why deleting may remove `change_log` rows when D4 says never to:* D4 is about
a living schedule's history while the team exists. Deleting the team is the
operator removing the tenant, not editing its history; there is nobody left
for that history to serve.

**⚠️ The default operator password is committed** (it is the settings
password's default). That was already true of the settings panel, which can
repoint the database; the console can now also delete teams. Set
`PAKASH_SETTINGS_PASSWORD` or `PAKASH_ADMIN_PASSWORD` in any real deployment.

## D29 — The manager hears a submission as it happens

> **Update:** the per-process limitation below is resolved by D35 — signals
> cross processes over PostgreSQL `LISTEN/NOTIFY` (`dal/notify.py`). The same
> SSE line now also carries a bare `chat` signal, so a streaming manager-chat
> reply is re-read at once.

When an employee submits or withdraws a constraint request, or answers or
withdraws a swap, the manager's open screen re-reads that inbox within a
second, and the existing pop-up announces it. Before this, the screen polled
every 15 seconds, so a request could sit unannounced for that long while
the manager was looking straight at the board.

**It is a Server-Sent Events stream, boss-only**
(`GET /api/schedule/requests/events`). An employee route publishes to it only
after its write succeeded. A refused submission wakes nobody.

**A signal carries no data.** It names an inbox (`requests` or `swaps`) and
nothing else. The browser re-reads through the routes it already used, behind
the same `guards.boss()`. So the stream adds *when* without adding a second
*what*, and there is no new read path that would need its own scoping or
could leak a colleague's stated reason.

**It does not cross [D16](#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)
or [D17](#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes).**
Those refuse a *delivery channel*: something that reaches a person who has
not opened the app, through an address the product does not hold. This
reaches only a manager's own open tab, which is the same "the app telling
someone while they are looking at it" that D16 already allows.

**The stream ends itself every five minutes** and `EventSource` reconnects.
The reconnect passes through the guard again, so a team suspended under
[D28](#d28--teams-are-opened-by-צוות-משמרות-זהב-not-by-whoever-reaches-the-login-page-️-amends-d10)
stops listening within minutes rather than holding an authorised stream
forever.

**⚠️ Per process, like `LoginThrottle`.** `common/events.py` is in-memory. A
submission handled by another worker does not reach this worker's streams.
The 15-second poll stays underneath as the backstop, so a dropped stream or
a second worker degrades to the old behaviour rather than to silence. If the
backend ever runs several workers, Postgres `LISTEN/NOTIFY` is the upgrade.

---

## D30 — Model calls are traced to Opik, prompts and replies included

> **Removed.** Opik tracing (`dal/llm/tracing.py`, the `opik` dependency, its
> settings and compose variables) was taken out: the deployment runs on an
> air-gapped network, and nothing but the model server may be called. The
> `pakash.llm` log line (counts and timings only) remains. The move to
> Python 3.11 stays.

With `OPIK_API_KEY` set, every `complete_json` is one trace in Opik, named by
its flow, with each HTTP completion under it as an LLM span: messages, reply,
model, tokens, duration, and the error when it failed
(`dal/llm/tracing.py`). Without the key nothing is sent and nothing changes.

**This is a deliberate exception to "never log full prompts".** Prompts carry
employee names, stated reasons for absence and the manager's own sentences
about their staff, and with the key set they leave the machine for the
configured Opik workspace (Comet's hosted Opik unless `OPIK_URL_OVERRIDE`
points at a self-hosted one). The boss chose this knowingly: a token count
can say a call was expensive but never *why the model answered that*, and
that is the question every prompt fix starts from.

The exception is narrow:

- **Opik only, and only behind the key.** The `pakash.llm` log line stays
  counts and timings (`telemetry.py`). No other log, error or response gains
  prompt text because tracing exists.
- **Env-only and read at start-up.** Not in the settings panel: a team
  manager must not be able to start shipping every team's prompts to an
  account of their choosing. Turning it on is the operator's act.
- **It never fails a call.** A tracing error is logged and the call runs
  untraced.

*Why Python moved to 3.11 in the same change:* Opik's SDK dropped 3.8 long
ago, and the 3.8.10 pin was already the costliest line in the build (EOL
Debian, compiling `backports.zoneinfo`). See BUILD_ORDER.md.

## D31 — Structured schedules may be assigned by code ⚠️ *(amends D3; superseded by D34)*

The manager can choose `AI`, deterministic `code`, or `auto` for schedule
generation. Code uses the existing availability, qualification, staffing,
rest, load and rotation arithmetic and spends zero model tokens.

**The boundary is representability, not roster size.** Code runs only when
all placement inputs are structured. Explicit code mode refuses semantic
input and never silently drops context. In auto mode, a small model call may
compile an exact instruction into one of two validated operations: a named
employee is unavailable, or a named employee is required, for one existing
shift on one existing date. Code then builds the roster. Every semantic
source must be accounted for, and the server rejects invented people, shifts,
dates and unsupported operations. Ambiguous rules, preferences, policy,
training judgment, incomplete translation and a deterministic result with
warnings fall back to the full scheduling model.

This is the narrow exception to D3. The translator is a compiler into existing
structured inputs, not a second rule engine and not an assignment agent. It
does not make warnings blocking for an AI answer. Hybrid results report their
translation token usage and carry a reason per assignment; every result remains
an ordinary draft the manager may inspect and edit. The selected engine is
stamped when the build opens; changing the setting affects the next build.

## D32 — A standing sentence is translated once, and the translation is kept *(amends D31, D21)*

D31's translator ran on every build: the same rule, policy and note were
sent to the model for every week and every span, and a policy code cannot
represent (`rest_policy`) was sent, failed and fell back to the full
scheduler every time. Now a **standing** source — a rule, a policy, an
employee's note, an active preference; everything but the build's own
instruction — is translated once and kept in `compiled_sources`.

**The sentence stays the source.** A kept translation is a derivative,
looked up by the words (`source_key`), the roster and shift names
(`vocab_key`) and the compiler (version + prompt). Editing the sentence,
changing the roster or the prompt simply stops matching. D2 holds: rules
stay the manager's sentences, and D21 holds: a preference still authorises
nothing. What changed is that D31 gave both a structured vocabulary to be
*read into* for code, and reading one is now done once.

**Setup is translated when it is saved.** The save stays zero-token and
synchronous; it queues one `compile_sources` job, and the worker translates
what is missing. No model, or a failed job, costs nothing: the next build
translates as it did before.

**A negative is kept too.** A binding source the model marked `unresolved`
sends later builds straight to the full scheduler without a translation
call. What *code* refused, or the model skipped, is not kept — it is tried
again.

**Time is anchored to when the sentence was written.** "עודד חולה 3 או 4
ימים" is read against `source_anchors.anchored_on`, the day the sentence
was first seen, which does not move when it is compiled again. The model
gives the certain range (hard), the uncertain day (soft, weight 3) and a
question for the manager; code checks a relative range lies within 90 days
of the anchor and an absolute one within the dates the sentence writes, and
refuses to keep a recurring sentence spread over one period's dates.

**Policies became translatable (step 2).** Four request kinds were added so
the policies that used to be kept as unresolved can be read into code:
`min_rest`, `max_consecutive`, `balance` and `requires_with`, the first
three allowed to name nobody (the whole team). A policy is translated clause
by clause and left unresolved whole if any clause has no kind — training,
rotation restated, "use judgement". `COMPILER_VERSION` moved to 2 so every
kept negative is read again. `balance` is a ranking, not a guarantee: it is
weighed like any soft wish, and is not reported as broken. Trainees are
still not placed by code, so a training policy still goes to the full
scheduler.

**Shown, not edited.** Setup lists what code made of each sentence:
translated, needs AI (with the reason), a wish code will not weigh,
translating, or expired. Correcting a reading means rewording the sentence.

---

## D33 — Redis shares process-local state, and is never required *(superseded by D35)*

Two things lived in each process's memory: the login throttle and the
manager's live "an inbox moved" signals (D29). With more than one process --
several API workers, or the API beside `app.worker` -- each kept its own
copy: N workers allowed N times the guesses, and a signal raised on one
worker never reached a manager streaming from another.

**With a Redis URL saved, both are shared** (`common/redis_hub.py`): the
throttle counts and locks in Redis keys, and signals go out on a per-team
pub/sub channel that one listener thread per process relays to its streams.

**The model queue moves to Redis too** (`dal/llm/redis_slots.py`), taking
over from `PostgresModelSlots` whenever Redis is reachable. It keeps that
contract -- one deployment-wide limit read live from `llm_max_concurrency`,
one call in flight per team -- and adds the one thing advisory locks polled
in a loop could not give: order. Tickets are served by priority, then
arrival, so a manager's chat goes ahead of a queued build day. Holders renew
a 30-second lease and waiters refresh their ticket, so a killed process
frees its place within a lease. The PostgreSQL slots stay as the fallback.

**Redis is an accelerator, not a dependency.** URL empty is the default.
Without Redis, or when it stops answering, the throttle and the signals
return to memory and the queue to PostgreSQL. A login must never fail
because a cache is down.

The URL, password and key prefix are runtime settings, editable in the panel
with a connection test that shows the server and what this app keeps in it:
active model calls, the queue, locked accounts. A save reaches the other
processes because the hub re-reads the settings file every few seconds.

## D34 — A constraint solver assigns every schedule; the model only translates ⚠️ *(supersedes D31, replaces D3 for assignment)*

The manager asked to rebuild the engine around what the field has settled
on for rostering: a language model for language, a solver for the
arithmetic. Who works which shift is a combinatorial optimisation, and a
model filling it day by day was the slowest and least reliable part of the
product — a prompt per day or week, repair calls, capacity splitting, and a
greedy fallback that could spend a person on Monday whom Tuesday needed.

**OR-Tools CP-SAT assigns a whole span in one solve** (`bl/solver/`): one
boolean per legal (person, slot) pair. A placement that breaks a hard
availability, the rotation or closure cycle, eligibility or a hard `avoid`
is never a variable. The audit's blocking checks — rest, runs of days,
weekly hours — and every hard structured request are constraints. The
objective is solved in two phases: coverage first (unfilled seats, missing
roles, the shift manager), then, without giving any of that back, soft
wishes and soft availability, closers on their own closure, an even share of
hours and nights, and a day off between shifts. Spans are up to four weeks;
a longer period is solved in such blocks, each seeing the ones before it.

**The model's only job in a build is translation.** The `DirectiveAgent`
(D32) turns instructions, rules, policies, notes and preferences into
validated absences, pins and structured requests. A sentence that does not
translate — binding or not — is never sent to a full AI scheduler; there is
none. The schedule is built without it and its `notes` name it, so the
manager can restate it or record it as a constraint. Structured input needs
no model call at all.

**What stays from D3.** The audit is still arithmetic, still advisory, and
still the one definition of every countable fact; the solver is built from
the same thresholds so a solved schedule is clean by the same measure that
grades it. The manager still decides: every result is an ordinary draft
with a reason per row (D8), every hand placement is a pin, and a seat
nobody can legally fill is reported rather than refused. The chat, the
change agent and the reason gates are unchanged.

**Operational-duty exception.** A separately recorded duty is occupied time,
not a preference the manager may knowingly override. The same interval
arithmetic is shown by the placement check, but assignment and move endpoints
also reject an overlap directly. This does not give the audit a veto: the
write precondition is enforced outside `bl/audit/`, while the audit continues
to report any older schedule that already contains the conflict.

**What changes.** "Hard" now means hard for generation: the solver will not
place a row that breaks a hard rule it can represent. Engines and call
widths (`ai`/`code`/`auto`, `day`/`week`) are gone; the panel holds the
solver's time limit and worker count instead. Among equally good schedules
the pick may differ between builds.

## D35 — PostgreSQL holds every piece of shared state *(supersedes D33)*

Redis held three things (D33). Each fits in the database every process
already shares, so the deployment has one stateful service, not two:

- **The login throttle** is a `login_attempts` table: a fixed window per
  account, a lock after the limit, swept as accounts recover.
- **Live inbox signals** are `LISTEN`/`NOTIFY` on a channel named after the
  schema, one listener connection per process (`dal/notify.py`).
- **The model queue** is the advisory-lock `PostgresModelSlots` that was
  already Redis's fallback: one deployment-wide limit, one call per team.

A database that stops answering drops the throttle and the signals back to
memory, as Redis being down did. A settings save made by another process is
picked up by the store itself within seconds, which the Redis hub used to
trigger. `llm_max_concurrency` now defaults to 4: the endpoints this runs
against are hosted or batching servers; a local Ollama should lower it to 1.

---

## D36 — An absence is read and planned in code, and the fairest cover is proposed *(amends the chat's "the manager chooses" rule)*

"עודד חולה בשני ושלישי", "עודד טס לחו״ל", "ירין לא יכולה לעבוד בשישי" are the
commonest things a manager types, and each cost three or four full model
rounds -- the whole prompt, profile, period and transcript re-sent each time
-- to reach what is a lookup and arithmetic: who, which dates, their shifts,
who is free (D3).

**`bl/absence/` answers these with no model.** It reads one roster name, an
absence phrase and every date the sentence names (lists, ranges, weekdays in
the week on screen, "השבוע"). What it cannot place with certainty -- two
names, a named shift, a hypothetical, a pairing wish -- goes to the model
unchanged. A missing date is one question ("באילו תאריכים?"); a bare weekday
on a "can't work" sentence is one question with two buttons (this Friday, or
every Friday as a standing constraint).

**The plan carries the fairest cover rather than waiting for a pick.** Each
affected shift's candidates come from `find_replacements` (clean only), are
ranked by hours, then shifts, then nights in the period, and the load is
recounted after every pick so one person does not absorb the whole absence;
each pick is re-audited beside the earlier ones. This reverses the chat
prompt's "wait for the manager to choose" for this path only, and is safe
for the same reason any plan is: nothing is written until the manager
approves, the alternatives are shown under the plan, and choosing one
rebuilds it in code. A manager's own pick wins over the fair one.

**Not a second write path.** The plan is built by handing
`ChatPlanBuilder.prepare` the turn the model would have returned, so it
passes every check and audit a model plan does. The replacement tab reads
only (`GET /api/agent/replacements`); its picks become a plan by being sent
to the conversation, where approval is the one write (D12/D19).

**Answered in the request.** `start_turn` runs the code paths inline, so a
code-answered turn comes back finished in the send response with no worker
pickup and no poll. The queued job still runs and finds the turn finished.

## D37 — A new soldier or a new shift is absorbed into the drafts already built *(amends "a saved change applies to the next build")*

A client asked that adding a person or a shift fit them into the board
already built while keeping almost everything where it was. Until now a
profile save applied only to the next build, and rebuilding a range
replaced every generated row on it: one new soldier reshuffled 21 of 28
rows in a test week.

**The solver keeps what stands** (`solver/stability.py`). A rebuild handed
`keep` rewards each existing row for staying where it is, priced at half
of what moving that shift from somebody above the even share to somebody
below it gains in evenness. So a shift moves from an overloaded person to
an underloaded one (the newcomer), and never from somebody already at
their share. In the same test week the newcomer took exactly four shifts,
one from each of the four people carrying five, and nothing else moved; a
new night shift on a roster able to staff it moved nothing at all.
Coverage is still settled first (D34), so a kept row never holds a seat
empty, and a kept row keeps the reason it was placed with (D8).

**Saving the profile starts it.** A save that adds an active person or a
shift opens a `keep_existing` range job on every draft from today (or its
first day) to its end; the shift's slots are added to the stored grid
first. A published week is never touched, only listed as skipped, since
changing what the team was shown needs the manager to unpublish it; a
draft with nothing on it is left alone. The same happens after a profile
plan is approved in the chat. A refit that cannot start never fails the
save. The build dialog offers the same refit by hand ("שמירה על השיבוץ
הקיים").

## D38 — A stuck model call fails, and a team may run several at once *(amends D35's one-call-per-team quota)*

Every chat message and build of a team sat on "ממתין למודל…" behind one
call the model server never answered. Three things combined: `llm_timeout_
seconds` defaulted to 0, meaning no read limit for chat; each team could hold
one model call at a time; and only one worker lane took chat turns.

- **0 is the built-in ceiling, not "forever".** 300s for chat and every
  other flow, 900s for a build's translation. A read timeout is not retried,
  and the SDK's own retries are off, so a stuck call fails once with a
  Hebrew error and releases its slot.
- **A team may use every global slot** (`llm_team_concurrency`, 0 by
  default). Set it on a deployment shared by several busy teams.
- **Three chat lanes of six worker threads**, so one slow turn does not hold
  every other manager's; the pool grows to 16 to carry them.

What this gives up: a model genuinely slower than five minutes per chat
answer now fails, and `llm_timeout_seconds` must be raised for it. A
server that serves one request at a time queues concurrent calls itself,
and a call waiting in its queue counts against the same ceiling.

## D39 — Replicas agree through PostgreSQL, not a shared disk or a variable *(completes D35)*

Running four API pods and three frontend pods showed what D35 left per
process. Two things broke without an error:

- **The session key.** Unset, each process generated its own, so a cookie
  issued by one pod was refused by the next and bosses were logged out at
  random. The start-up guard only counted workers inside one process
  (`WEB_CONCURRENCY`), so four pods of one worker each passed it.
- **Panel settings.** They were a JSON file on a volume. Pods rarely share a
  disk, so a save applied on the pod that took it and nowhere else.

Both now live in a `deployment_state` table. The session key, when
`PAKASH_SESSION_SECRET` is unset, is generated once and claimed with an
insert the first process wins; every other reads it back on first use, not
at import, so a pod may start before its database. A panel save is written
there with a version, and every process polls it on the file's existing
three-second cadence. The `database_*` fields stay in the file and the
environment: they are what the poll connects with. A file saved before
this seeds an empty table once.

`initialize()` also runs under an advisory lock now: replicas starting
together raced through the same `CREATE ... IF NOT EXISTS`, and Postgres
answers the loser with a unique violation.

What this gives up: the session key sits in the database in the clear, next
to everything it protects; an operator who wants it elsewhere sets the
variable. A process with no database still generates its own key, and is
refused with more than one worker.

## D40 — A seat a chat change vacates is filled by the solver *(amends the chat's "the manager chooses" rule, extends D34)*

A `changes` plan that takes somebody off a shift used to leave the seat
empty unless the model named a replacement, and the model was told to wait
for the manager's pick — so a constraint chat could loop asking "who will
replace her?" while the absence itself was never planned.

**The model names who leaves; the solver picks who comes in.** When a plan's
removals leave a slot with fewer people than it had, `bl/chat_vacancies.py`
hands the touched dates to the solver: every other row there is a pin, the
person who left (and anyone the plan marks unavailable) is a hard `avoid`,
and only the solver's picks on vacated slots join the plan as `assign`
operations, listed under the reply. A model-picked cover for a seat the
same plan vacates is dropped in favour of the solver's; a pick that replaces
nobody is still asked about. `leave_vacant` keeps a seat empty on request.
Chat builds use the saved solver settings, like the board's.

**Still one write path.** It is a plan like any other: shown, audited, and
applied only on the manager's approval (D8/D19). A seat nobody can legally
fill is reported in the reply, never filled against a rule.

## D41 — The system settings live only in the operator console *(amends D28)*

The settings gear and the account-menu entry are gone from the team screen;
the model, solver and database settings are edited only from the צוות
משמרות זהב console's "מערכת" tab, on the operator session. They are shared
by every team, and a team manager editing them moved the ground under
everyone else. `/api/settings` still admits a boss session that sends the
settings password, for scripts; no team UI uses it.

---

## D42 — Import is back: a sheet's shape is data, found by code, the model or the manager *(revives D7)*

Importing was removed (D7) because a reader per shape could not keep up:
every file that predated the app came in a shape of its own — dates down or
across, people or shifts as lanes, weekday names with no dates, weeks
stacked on one sheet — and each needed another class.

**The shape is now a `Layout`, not a class.** Which way time runs, the line
holding the dates, an optional shift line nested under them, what a lane is
(`shifts`, `people` or `none`), where data starts and ends, and the sheet's
own markers for "away" and "nothing". One reader (`bl/importer/reader.py`)
reads any sheet given one. Turning the sheet on its side is a transpose, so
"length or width" costs nothing.

**Three sources answer "what is the layout", and one scorer judges them.**

1. *The manager*, on the confirm screen: a few fields, or one click on an
   alternative reading. Read as given.
2. *Detection* (`detect.py`): every plausible layout, both orientations,
   read and scored by how much of the sheet resolves to **people on the
   roster and shifts the profile declares**. No model call.
3. *The model* (`mapper.py`, flow `import`), asked only when detection is
   below 75% sure, finds nothing, or the manager described the file in
   words. It sees the sheet's corner and returns a layout — **never rows**.
   Its layout is read and scored by the same code and used only if it
   explains the sheet at least as well.

So the model can make reading flexible without being able to place anybody:
who works when is still read by code, cell by cell, and checked against the
roster (D34's division, applied to files).

**Names are matched, never guessed** (`roster.py`): "שובל ק." is שובל קרמר,
"יוסי ב." is a roster that only says יוסי, "קרמר" alone with two Kramers is
a question. The screen maps any name or shift heading to someone, or leaves
it out, and the file is re-read with that mapping.

**Preview writes nothing; confirm stores what was shown** (D7 unchanged).
A confirm opens a new period, or — when the manager chose an overlapping
draft — rewrites only the imported shifts on the imported dates of that
draft. A published period is never written into. Rows carry
`source='imported'` and a reason naming the file; absences the sheet stated
become the manager's constraints.

**What a real unit's file added** (Sample C in `FILE_FORMATS.md`): a
header line decides for itself whether its dates are day or month first,
since one copy of the same sheet writes `13/10/2024` and another
`10/13/2024`; `בית` is an absence like `חופש`; a handover word
(`חפיפה`) is a note on the row, not part of a name; a sheet up to 1,500
columns wide is read, and one holding more than an import may store opens
on the month covering today, with any other run of dates a field away; a
workbook with a tab per month opens on the tab covering today. Unit 619's
own tab (Sample D) added dates as `01-מרץ` with the year chosen on screen,
a personal-number column that labels nobody, legend and banner rows, and
cells naming a place with the shift in brackets — read as headings the
manager maps to a declared shift, to an absence, or to nothing.

What this gives up: a layout is one shape per sheet. A sheet mixing two
unrelated tables needs its data range narrowed (`first_line`/`last_line`)
or splitting. Colours carry no meaning to the importer.

---

## Open

- *(none)* — the Python version is settled at **3.11** (D30).
