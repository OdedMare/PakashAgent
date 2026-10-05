"""The workplace profile the interview fills in, as a JSON schema.

Also the field lists the draft is merged by. Every profile field the interview
may fill is named here; a field absent from these lists would be silently
dropped every turn.
"""

PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "workplace", "employees", "shifts", "dependencies", "rules",
        "availability_process", "constraint_deadline", "casual_worker_policy",
        "training_policy", "audit_policy", "rest_policy", "weekend_policy",
        "fairness_policy", "conflict_policy", "existing_schedule_source",
        "summary",
    ],
    "properties": {
        "workplace": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "name", "mission", "success_criteria", "timezone",
                "operating_days", "planning_horizon", "scheduler_name",
                "scheduler_works_shifts", "rotation_mode",
                "first_closure_group", "first_closure_date",
                "round_first_closure_group", "round_first_closure_date",
                "triplet_first_closure_group", "triplet_first_closure_date",
            ],
            "properties": {
                "name": {"type": "string"},
                "mission": {"type": "string"},
                "success_criteria": {
                    "type": "array", "items": {"type": "string"},
                },
                "timezone": {"type": "string"},
                "operating_days": {
                    "type": "array", "items": {"type": "string"},
                },
                "planning_horizon": {"type": "string"},
                "scheduler_name": {"type": "string"},
                "scheduler_works_shifts": {"type": "boolean"},
                "rotation_mode": {
                    "type": "string", "enum": ["round", "triplet"],
                },
                "first_closure_group": {"type": "string"},
                "first_closure_date": {"type": "string"},
                "round_first_closure_group": {"type": "string"},
                "round_first_closure_date": {"type": "string"},
                "triplet_first_closure_group": {"type": "string"},
                "triplet_first_closure_date": {"type": "string"},
                "general_exit_schedule": {"type": "string"},
                "enabled_exit_patterns": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["triplet", "hamshushim", "shushim"],
                    },
                },
                "rotation_a_unavailability": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "days", "shifts", "start_time", "end_time",
                            "reason",
                        ],
                        "properties": {
                            "days": {
                                "type": "array", "items": {"type": "string"},
                            },
                            "shifts": {
                                "type": "array", "items": {"type": "string"},
                            },
                            "start_time": {"type": "string"},
                            "end_time": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
        },
        "employees": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name", "role", "workload", "max_weekly_hours",
                    "eligible_shifts",
                    "is_shift_manager", "is_trainee",
                    "counts_toward_staffing", "can_train", "trainers",
                    "is_casual", "availability", "recurring_constraints",
                    "rotation_group", "service_type",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "workload": {"type": "string"},
                    "max_weekly_hours": {"type": "number", "minimum": 0},
                    "eligible_shifts": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "is_shift_manager": {"type": "boolean"},
                    "is_trainee": {"type": "boolean"},
                    "counts_toward_staffing": {"type": "boolean"},
                    "can_train": {"type": "boolean"},
                    "trainers": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "is_casual": {"type": "boolean"},
                    "rotation_group": {"type": "string"},
                    "exit_pattern": {
                        "type": "string",
                        "enum": ["round", "triplet", "hamshushim", "shushim"],
                    },
                    "notes": {"type": "string"},
                    "service_type": {
                        "type": "string",
                        "enum": ["standard", "overlap", "reserve"],
                    },
                    "availability": {"type": "string"},
                    "recurring_constraints": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "days", "shifts", "available",
                                        "is_hard", "start_time", "end_time",
                                        "reason",
                                    ],
                                    "properties": {
                                        "days": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "shifts": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "available": {"type": "boolean"},
                                        "is_hard": {"type": "boolean"},
                                        "start_time": {"type": "string"},
                                        "end_time": {"type": "string"},
                                        "reason": {"type": "string"},
                                    },
                                },
                            ],
                        },
                    },
                },
            },
        },
        "shifts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name", "purpose", "start_time", "end_time", "days",
                    "staffing", "is_on_call", "hour_weight",
                    "fairness_weight", "shift_type",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "purpose": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "days": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "staffing": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["days", "headcount", "required_roles"],
                            "properties": {
                                "days": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "headcount": {"type": "integer", "minimum": 0},
                                "required_roles": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "is_on_call": {"type": "boolean"},
                    "hour_weight": {"type": "number", "minimum": 0},
                    "fairness_weight": {"type": "number", "minimum": 0},
                    "requires_shift_manager": {"type": "boolean"},
                    "shift_type": {
                        "type": "string",
                        "enum": ["regular", "overlap", "on_call"],
                    },
                },
            },
        },
        "dependencies": {
            "type": "array", "items": {"type": "string"},
        },
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "priority"],
                "properties": {
                    "text": {"type": "string"},
                    "priority": {"type": "string", "enum": ["hard", "soft"]},
                },
            },
        },
        "availability_process": {"type": "string"},
        "constraint_deadline": {"type": "string"},
        "casual_worker_policy": {"type": "string"},
        "training_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "shadow_shift_fraction", "shadow_shifts_per_week",
                "alternate_halves", "counts_toward_staffing",
            ],
            "properties": {
                "shadow_shift_fraction": {
                    "type": "number", "minimum": 0, "maximum": 1,
                },
                "shadow_shifts_per_week": {"type": "integer", "minimum": 0},
                "alternate_halves": {"type": "boolean"},
                "counts_toward_staffing": {"type": "boolean"},
            },
        },
        "audit_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "max_weekly_hours", "max_consecutive_days", "min_rest_hours",
            ],
            "properties": {
                "max_weekly_hours": {"type": "number", "minimum": 0},
                "max_consecutive_days": {"type": "integer", "minimum": 1},
                "min_rest_hours": {"type": "number", "minimum": 0},
            },
        },
        "rest_policy": {"type": "string"},
        "weekend_policy": {"type": "string"},
        "fairness_policy": {"type": "string"},
        "conflict_policy": {"type": "string"},
        "existing_schedule_source": {"type": "string"},
        "summary": {"type": "string"},
    },
}


# Every profile field the interview may fill. The draft is merged field by
# field across turns, so this is the list that decides what "carried forward"
# means — a field absent here would be silently dropped every turn.
TEXT_FIELDS = (
    "availability_process", "constraint_deadline", "casual_worker_policy",
    "rest_policy", "weekend_policy", "fairness_policy", "conflict_policy",
    "existing_schedule_source", "summary",
)
LIST_FIELDS = ("employees", "shifts", "dependencies", "rules")
OBJECT_FIELDS = ("workplace", "training_policy", "audit_policy")
