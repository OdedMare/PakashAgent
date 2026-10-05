"""What every route group under `/api/schedule` is built from."""

from fastapi import APIRouter


class RouteGroup:
    """A cohesive set of routes registered onto the shared schedule router.

    Each group states its own guard on every route -- `boss` for anything
    that writes or reads drafts, `visitor` for the few reads a member may
    make -- rather than inheriting one from a prefix (D5).
    """

    def __init__(self, service, boss, visitor):
        self.service = service
        self.boss = boss
        self.visitor = visitor

    def register(self, router: APIRouter) -> None:
        raise NotImplementedError
