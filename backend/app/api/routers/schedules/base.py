"""What every route group under `/api/schedule` is built from."""

from fastapi import APIRouter

from app.common.read_cache import NoCache


class RouteGroup:
    """A cohesive set of routes registered onto the shared schedule router.

    Each group states its own guard on every route -- `boss` for anything
    that writes or reads drafts, `visitor` for the few reads a member may
    make -- rather than inheriting one from a prefix (D5).
    """

    def __init__(self, service, boss, visitor, cache=None):
        self.service = service
        self.boss = boss
        self.visitor = visitor
        # Heavy reads kept until the team's data changes (D50).
        self.cache = cache or NoCache()

    def register(self, router: APIRouter) -> None:
        raise NotImplementedError
