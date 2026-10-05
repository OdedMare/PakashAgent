"""Persistence around the stateless intro interview.

`IntroInterview` decides what to ask; this decides what to remember. Keeping
them apart is what lets the interview stay a pure function of the
conversation, testable against a fake model without a database. The session
owns the state, so a boss who refreshes -- or opens the app on a second
machine -- resumes the profile they had.

Every method takes the team from the signed session cookie and passes it to
the repository, which filters on it.

| Module | Owns |
|---|---|
| `service.py` | `InterviewService`: start, answer, resume, end |
| `history.py` | What the stored turns imply for the next model turn |
| `responses.py` | The shapes a session is served in |
| `seeding.py` | Seeded drafts and the ended-early `completeness` record |
"""

from app.bl.interview_service.service import InterviewService

__all__ = ["InterviewService"]
