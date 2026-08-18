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

## Open

- **Python version.** `AiSummryIO` pins **3.8.10** (EOL), likely a deployment
  constraint there. Mirroring it unless PakashAgent targets a newer environment —
  the boss hasn't answered. If 3.8.10 holds: no `X | Y`, no `list[str]`, no
  `match`; use `Optional`, `List`, `Dict`.
