"""Manual editing of the complete workplace profile.

| Module | Owns |
|---|---|
| `service.py` | `ProfileService`: update, and confirmed agent operations |
| `roster.py` | Employees, exit patterns, rotation groups |
| `shifts.py` | Shift hours, staffing groups, shift types |
| `identity.py` | Renaming a soldier or a shift, deleting a soldier: carried through the profile |
| `retire.py` | Deleting a shift type: archived, and cleaned out of the roster |
| `workplace.py` | The workplace block, anchors, rules, audit policy |
| `validation.py` | Shared validators |
"""

from app.bl.profile_service.service import ProfileService

__all__ = ["ProfileService"]
