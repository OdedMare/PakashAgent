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
