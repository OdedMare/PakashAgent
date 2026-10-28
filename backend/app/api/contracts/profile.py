"""Editing the workplace profile."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ProfileUpdate(BaseModel):
    """A manual profile patch, including first-time setup without a model."""

    workplace: Optional[Dict[str, Any]] = None
    employees: Optional[List[Dict[str, Any]]] = None
    shifts: Optional[List[Dict[str, Any]]] = None
    rules: Optional[List[Dict[str, Any]]] = None
    dependencies: Optional[List[str]] = None
    training_policy: Optional[Dict[str, Any]] = None
    audit_policy: Optional[Dict[str, Any]] = None
    availability_process: Optional[str] = None
    constraint_deadline: Optional[str] = None
    casual_worker_policy: Optional[str] = None
    rest_policy: Optional[str] = None
    weekend_policy: Optional[str] = None
    fairness_policy: Optional[str] = None
    conflict_policy: Optional[str] = None
    existing_schedule_source: Optional[str] = None
    summary: Optional[str] = None
    # The `profile_revision` the form was loaded at. A save from a form that
    # somebody else has saved over since is refused (409) instead of undoing
    # their edit; omitted, the save is not checked against the form.
    expected_revision: Optional[int] = None


class RotationPreviewRequest(BaseModel):
    """The setup screen's unsaved rotation, to preview its coming weekends."""

    workplace: Dict[str, Any]
    shifts: List[Dict[str, Any]] = []
    start: Optional[str] = None
    weeks: int = 8
