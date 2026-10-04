"""Employee identity and the one thing an employee may write.

Both halves of [D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10),
which reversed D5 and amended D10 deliberately. Before it, a member was a
holder of a shared link and nothing more -- indistinguishable from every other
member, which is why "his hours" could not be expressed at all.

- **`employee_identities`** (`identity_claims.py`) -- a claim over a NAME from
  the workplace profile, protected by a personal passcode. Not a user record:
  `employee` matches `assignments.employee` exactly, because the whole product
  identifies people by the name the interview recorded.
- **`constraint_requests`** (`constraint_requests.py`) -- a submission awaiting
  the manager. Deliberately NOT a row in `availability`, so asking cannot move
  the arithmetic (D3). Approval is a manager action.
- **`swap_requests`** (`swap_requests.py`) -- a trade two employees agreed to,
  awaiting the manager.

Passcodes reuse `teams.hash_password` rather than a second scheme: one
password format in the codebase means one place to change it.
"""

from app.dal.repository.constraint_requests import ConstraintRequestRepository
from app.dal.repository.identity_claims import EmployeeIdentityRepository
from app.dal.repository.request_status import (  # noqa: F401
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_DECLINED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_WITHDRAWN,
)
from app.dal.repository.swap_requests import SwapRepository


class IdentityRepository(
    EmployeeIdentityRepository, ConstraintRequestRepository, SwapRepository,
):
    """Identities, constraint requests and swaps, composed."""


__all__ = [
    "IdentityRepository",
    "STATUS_PENDING", "STATUS_APPROVED", "STATUS_REJECTED", "STATUS_WITHDRAWN",
    "STATUS_AWAITING", "STATUS_DECLINED",
]
