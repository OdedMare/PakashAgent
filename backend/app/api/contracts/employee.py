"""The employee's own area (D14)."""


from pydantic import BaseModel, Field



# -- the employee's own area (D14) -----------------------------------------
#
# Note what is absent from every request body below: the employee's name.
# It is taken from the signed session cookie instead, because a name in the
# body is a name the sender chooses -- and that would let any signed-in
# employee read a colleague's hours or submit a constraint as them.


class ClaimRequest(BaseModel):
    """Claim a roster name and set a personal passcode.

    Requires a valid share-link session to reach, and the name must be one
    the interview actually recorded — a free-text claim would let anyone
    holding the link invent an employee.
    """

    employee: str = Field(min_length=1, max_length=120)
    passcode: str = Field(min_length=4, max_length=200)


class EmployeeLoginRequest(BaseModel):
    """Sign in as a claimed identity."""

    employee: str = Field(min_length=1, max_length=120)
    passcode: str = Field(min_length=1, max_length=200)


class ConstraintSubmission(BaseModel):
    """An employee asking not to be scheduled (or offering to be).

    A *request*, not a constraint: it lands as pending, is invisible to
    `bl/audit.py`, and changes nothing until the manager approves it (D14).
    `reason` is the employee's own words — the context a manager otherwise
    never gets in writing.
    """

    constraint_date: str = Field(min_length=1)
    shift_name: str = Field(default="", max_length=120)
    available: bool = False
    reason: str = Field(default="", max_length=1000)


class RequestDecision(BaseModel):
    """The manager ruling on a submission.

    `reason` is required to reject and optional to approve — a rejection that
    says nothing is how a submission channel stops being used, while an
    approval speaks for itself.
    """

    reason: str = Field(default="", max_length=1000)


class SwapProposal(BaseModel):
    """One employee offering another a trade of shifts.

    Both shifts are named by **assignment id**, not by date and shift name.
    The employee picks two cells off a grid they are already looking at, and
    ids mean the request can only ever name shifts that are really on the
    published schedule — a date-and-name pair could describe a slot that does
    not exist, or one belonging to somebody else.

    Nothing here moves an assignment. It lands awaiting the colleague's
    answer, and even their agreement only puts it in the manager's inbox
    (D14 — the manager remains the sole decider).
    """

    assignment_id: str = Field(min_length=1, max_length=64)
    counterparty: str = Field(min_length=1, max_length=120)
    counterparty_assignment_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=1000)


class SwapAnswer(BaseModel):
    """The colleague's reply to an offer.

    `agreed` false is a decline, which ends the swap — distinct from the
    manager's rejection, because which of the two people said no is a fact
    the requester needs in order to know whether to ask again.
    """

    agreed: bool


class ReleaseRequest(BaseModel):
    """Free a claimed name so it can be claimed again.

    The manager's tool for someone who left or lost their passcode. Rotating
    the share link does not do this — the link and the claim are separate
    credentials.
    """

    employee: str = Field(min_length=1, max_length=120)


class ReadAssignment(BaseModel):
    """One row as the importer read it, before anyone has confirmed anything.

    `shift` may be empty. A sheet of dates and people carries no shift
    information at all, and an empty name is how that absence stays visible
    instead of being silently answered with an invented one
    ([D9](../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
    The confirm screen is where the manager supplies it — which is why
    `ImportedAssignment`, the shape that comes *back*, requires it.
    """

    employee: str = Field(min_length=1, max_length=120)
    shift: str = Field(default="", max_length=80)
    date: str = Field(min_length=1, max_length=10)
    reason: str = Field(default="", max_length=1000)
