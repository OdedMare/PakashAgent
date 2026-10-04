"""The vocabularies schedule rows are validated against.

Where a row came from and what state a preference is in. Named once here so
the repository, `bl/`, and the tests all spell them the same way.
"""

# Where a constraint came from. `employee_reported` is the manager writing
# down what someone told them out of band -- employees have no account and
# never write here themselves (D5/D10), so this records provenance, not
# authorship.
SOURCE_MANAGER = "manager"
SOURCE_AGENT = "agent"
SOURCE_EMPLOYEE_REPORTED = "employee_reported"
SOURCE_INTERVIEW = "interview"
SOURCES = (
    SOURCE_MANAGER, SOURCE_AGENT, SOURCE_EMPLOYEE_REPORTED, SOURCE_INTERVIEW,
)

# Where an *assignment* came from (D18). A narrower set than the constraint
# sources above and deliberately a separate tuple: a schedule row can only
# have been generated, placed by the manager, or read out of a file, and
# widening this to the constraint vocabulary would admit values that mean
# nothing here. Like `availability.source`, it records where the row came
# from -- not who typed it.
ASSIGNED_BY_AGENT = "agent"
ASSIGNED_BY_MANAGER = "manager"
ASSIGNED_BY_IMPORT = "imported"
ASSIGNMENT_SOURCES = (
    ASSIGNED_BY_AGENT, ASSIGNED_BY_MANAGER, ASSIGNED_BY_IMPORT,
)

# What a stored preference is about. Presentation only -- the management
# screen groups on it and nothing in code branches on it, exactly as
# `briefing.KIND_*` works. Validated on write so the set stays a known one
# rather than whatever a caller happened to send.
PREFERENCE_STAFFING = "staffing"
PREFERENCE_NOTIFICATION = "notification"
PREFERENCE_EMPLOYEE = "employee"
PREFERENCE_SHIFT = "shift"
PREFERENCE_GENERAL = "general"
PREFERENCE_KINDS = (
    PREFERENCE_STAFFING, PREFERENCE_NOTIFICATION, PREFERENCE_EMPLOYEE,
    PREFERENCE_SHIFT, PREFERENCE_GENERAL,
)

# `suggested` is a proposal that changes nothing; `active` is in force;
# `archived` is turned off without losing the record that it was once true.
# Deleting is also possible -- archiving is for a preference the manager may
# want back, deleting for one that was a mistake.
PREFERENCE_SUGGESTED = "suggested"
PREFERENCE_ACTIVE = "active"
PREFERENCE_ARCHIVED = "archived"
PREFERENCE_STATUSES = (
    PREFERENCE_SUGGESTED, PREFERENCE_ACTIVE, PREFERENCE_ARCHIVED,
)
