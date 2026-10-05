"""The employee's own area: their identity, their hours, their requests.

The business half of D14:

- **Claiming a name** (`identity.py`) — the name must be one the interview
  recorded; a free-text claim would let anyone with the link invent a person.
- **The personal view** (`personal.py`) — hours, shifts, warnings computed by
  `bl/audit`, so the employee's arithmetic is the manager's arithmetic.
- **Requests** (`requests.py`, `swaps.py`) — submitting and withdrawing, and
  on the manager's side approving.

**Approval is the only thing that writes a constraint** (D3).
"""

from app.bl.employee_service.identity import IdentityService
from app.bl.employee_service.personal import PersonalView
from app.bl.employee_service.requests import ConstraintRequests
from app.bl.employee_service.swaps import SwapRequests


class EmployeeService:
    """The facade the employee routers talk to. Owns no behaviour itself."""

    def __init__(self, repository, schedules):
        self._identity = IdentityService(repository)
        self._requests = ConstraintRequests(repository, schedules)
        self._swaps = SwapRequests(repository, schedules)
        self._personal = PersonalView(repository, schedules, self._swaps)

    # -- identity --------------------------------------------------------------

    def roster(self, *args, **kwargs):
        return self._identity.roster(*args, **kwargs)

    def claim(self, *args, **kwargs):
        return self._identity.claim(*args, **kwargs)

    def login(self, *args, **kwargs):
        return self._identity.login(*args, **kwargs)

    def identities(self, *args, **kwargs):
        return self._identity.identities(*args, **kwargs)

    def release(self, *args, **kwargs):
        return self._identity.release(*args, **kwargs)

    # -- the personal view (D16) -----------------------------------------------

    def me(self, *args, **kwargs):
        return self._personal.me(*args, **kwargs)

    def acknowledge(self, *args, **kwargs):
        return self._personal.acknowledge(*args, **kwargs)

    # -- constraint requests ---------------------------------------------------

    def submit(self, *args, **kwargs):
        return self._requests.submit(*args, **kwargs)

    def withdraw(self, *args, **kwargs):
        return self._requests.withdraw(*args, **kwargs)

    def my_requests(self, *args, **kwargs):
        return self._requests.my_requests(*args, **kwargs)

    def pending(self, *args, **kwargs):
        return self._requests.pending(*args, **kwargs)

    def all_requests(self, *args, **kwargs):
        return self._requests.all_requests(*args, **kwargs)

    def approve(self, *args, **kwargs):
        return self._requests.approve(*args, **kwargs)

    def reject(self, *args, **kwargs):
        return self._requests.reject(*args, **kwargs)

    # -- swaps -----------------------------------------------------------------

    def propose_swap(self, *args, **kwargs):
        return self._swaps.propose_swap(*args, **kwargs)

    def answer_swap(self, *args, **kwargs):
        return self._swaps.answer_swap(*args, **kwargs)

    def withdraw_swap(self, *args, **kwargs):
        return self._swaps.withdraw_swap(*args, **kwargs)

    def my_swaps(self, *args, **kwargs):
        return self._swaps.my_swaps(*args, **kwargs)

    def incoming_swaps(self, *args, **kwargs):
        return self._swaps.incoming_swaps(*args, **kwargs)

    def pending_swaps(self, *args, **kwargs):
        return self._swaps.pending_swaps(*args, **kwargs)

    def all_swaps(self, *args, **kwargs):
        return self._swaps.all_swaps(*args, **kwargs)

    def approve_swap(self, *args, **kwargs):
        return self._swaps.approve_swap(*args, **kwargs)

    def reject_swap(self, *args, **kwargs):
        return self._swaps.reject_swap(*args, **kwargs)


__all__ = ["EmployeeService"]
