"""Names and limits shared by the schedule service's collaborators."""

# What the change log calls each kind of entry. Stored rather than derived so
# the history stays readable even as the code that wrote it changes.
ACTION_GENERATED = "generated"
ACTION_PUBLISHED = "published"
ACTION_MOVED = "moved"
ACTION_ASSIGNED = "assigned"
ACTION_REMOVED = "removed"
ACTION_SWAPPED = "swapped"
ACTION_CONSTRAINT = "constraint"
# A period opened empty for the manager to fill in themselves (D18). Distinct
# from `generated` on purpose: the history should say which of the two things
# in D6 happened, and both producing a schedule is exactly what makes them
# worth telling apart later.
ACTION_OPENED = "opened"
# A period read out of a file the workplace already had (D7). Distinct from
# both `generated` and `opened` for the same reason those are distinct from
# each other: the history should say where a schedule came from, and
# "imported from the manager's own spreadsheet" is a third origin.
ACTION_IMPORTED = "imported"

# How far back `learn_from_changes` reads. Generous, because a rule the
# manager keeps applying by hand shows up as a handful of corrections spread
# across months -- a short window would see one of each and find nothing. The
# rows are counted rather than sent, so the cost of a wide window is
# arithmetic, not context.
LEARN_HISTORY = 500

# The states a persisted range job can be in. Written into the schedule's
# `generation` document and read back by the browser, so they are named here
# rather than spelled out at every comparison.
GENERATION_RUNNING = "running"
GENERATION_COMPLETE = "complete"
GENERATION_FAILED = "failed"
GENERATION_PENDING = "pending"
# The manager stopped waiting. Distinct from `failed` on purpose: nothing
# went wrong, and the difference is what the board says to them. Both resume
# the same way -- from the first day that is not already complete.
GENERATION_CANCELLED = "cancelled"
GENERATION_FINISHED = (
    GENERATION_COMPLETE, GENERATION_FAILED, GENERATION_CANCELLED,
)

# How often a worker says it is still there.
#
# **This is what makes polling honest.** `llm_timeout_seconds` defaults to no
# limit, so a day held open by a model that is slow and a day held open by a
# model that is hung look identical from the outside -- both are simply
# "running", and the browser used to poll one of them forever. A beat every
# few seconds separates them: a job whose heartbeat is moving is working, and
# a job whose heartbeat has stopped has lost its worker (a restarted process,
# a killed thread) and can be relaunched by the next POST /run.
#
# Deliberately short relative to the client's staleness window: a beat is one
# tiny UPDATE, and missing four of them in a row has to mean something.
GENERATION_HEARTBEAT_SECONDS = 20

# How many times one span is re-asked before the job is called failed.
#
# **This is what stops a single blip from costing the whole build.** Every
# failure here was already checkpointed and retryable — but only by a person
# noticing and pressing continue, because the worker gave up on the first
# exception and the browser stopped polling a job marked `failed`. A dropped
# connection on day twelve of thirty left twenty-nine days of work parked
# behind a button nobody was watching.
#
# Bounded, because the failures that are not transient — a model that rejects
# the schema, a profile the grid cannot be built from — repeat identically and
# retrying them only burns the model server. Three is enough for a restarted
# Ollama or a proxy hiccup and short enough that a real error still surfaces
# within a minute.
MAX_SPAN_ATTEMPTS = 3
# Waited between attempts, geometric. The failure this is for is a model
# server that is briefly unavailable — mid-restart, or working through a
# queue — and answering the same second is how a retry hits exactly the state
# it backed off from. Capped so the pause never dwarfs the call.
RETRY_BASE_SECONDS = 2.0
RETRY_MAX_SECONDS = 15.0

# How long a fairness history read is reused across the spans of one build.
#
# It reads every *earlier* period, so by construction nothing inside the
# current build can change it — yet it was re-read, and re-joined, once per
# generated date. On a month at one call per day that is thirty scans of the
# team's whole history to compute a tally that was identical every time.
HISTORY_CACHE_SECONDS = 300
# Past assignments read for fairness before the scan stops.
HISTORY_ROW_LIMIT = 300
# Cached (team, before) entries kept before the cache is dropped.
HISTORY_CACHE_ENTRIES = 64

# What a manually placed row says for itself when the manager gave no
# sentence of their own. `assignments.reason` is NOT NULL and D8 is not
# relaxed here -- this states plainly that a person placed it, rather than
# manufacturing a judgment the agent never made. It is the same honesty
# `moved_from` applies to a dragged shift.
MANUAL_REASON = "שובץ ידנית על ידי המנהל"

# What an imported row says for itself. The agent made no judgment about it
# -- it is a record of what the workplace already did -- so claiming a reason
# here would be inventing one. `assignments.reason` stays NOT NULL and D8 is
# answered the same way the manual path answers it: by a different voice
# saying plainly where the row came from.
IMPORTED_REASON = "יובא מקובץ סידור קיים"

# Stored on a pinned row when a build opens with required assignments.
PINNED_REASON = "שיבוץ חובה שנבחר על ידי המנהל בעת בניית הסידור"

# How many change-log rows travel with a screen or a model call.
RECENT_CHANGES = 40

# Upper bounds on text stored inside a generation checkpoint.
INSTRUCTIONS_LIMIT = 2000
SUMMARY_LIMIT = 4000
ERROR_LIMIT = 1000
