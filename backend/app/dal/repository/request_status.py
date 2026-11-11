"""Lifecycle states for constraint requests and swaps, and passcode policy."""

# Request lifecycle. `withdrawn` is the employee taking it back before anyone
# ruled on it -- distinct from `rejected` because "I changed my mind" and "the
# manager said no" are different facts, and collapsing them would lose the
# only one of the two the employee controls.
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_WITHDRAWN = "withdrawn"
DECIDED = (STATUS_APPROVED, STATUS_REJECTED)

# A swap carries one state the constraint lifecycle has no need for: the
# stretch before the other employee has answered. It is not `pending`,
# because `pending` means "waiting on the manager" everywhere else in this
# module and the manager must not see an arrangement nobody has accepted.
STATUS_AWAITING = "awaiting_counterparty"
# The counterparty's refusal, kept apart from the manager's `rejected` for
# the same reason `withdrawn` is: three different people can end a swap, and
# collapsing them would lose which one did.
STATUS_DECLINED = "declined"

# A passcode short enough to be forgettable is worse than none, since it
# invites reuse of something guessable across a small team where everyone
# knows everyone.
MIN_PASSCODE = 4
