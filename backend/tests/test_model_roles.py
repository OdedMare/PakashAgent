"""Task-based model routing: flow → role → model, and the fallback.

The fallback is the whole backward-compatibility story — a deployment that
never opens the new settings must keep sending `llm_model` for everything —
so most of what is asserted here is that an unset role changes nothing.
"""

import pytest

from app.dal.llm.model_roles import (
    ADVANCED,
    DEFAULT,
    FAST,
    resolve_base_url,
    resolve_model,
    role_for_flow,
)


class _Settings:
    """Only the fields routing reads."""

    def __init__(self, **overrides):
        self.llm_model = "base-model"
        self.llm_model_fast = ""
        self.llm_model_default = ""
        self.llm_model_advanced = ""
        self.llm_base_url = "http://general/v1"
        self.llm_base_url_fast = None
        self.llm_base_url_default = None
        self.llm_base_url_advanced = None
        for key, value in overrides.items():
            setattr(self, key, value)


class _OldSettings:
    """A settings object from before roles existed — no role attributes at
    all, which is what a saved file or an older test double produces."""

    llm_model = "base-model"
    llm_base_url = "http://general/v1"


# --- flow → role -----------------------------------------------------------

@pytest.mark.parametrize("flow, expected", [
    ("scheduler", ADVANCED),
    ("interview", DEFAULT),
    ("changes", DEFAULT),
    ("planner", DEFAULT),
    ("learn", DEFAULT),
    ("briefing", FAST),
])
def test_each_flow_maps_to_its_role(flow, expected):
    assert role_for_flow(flow) == expected


def test_generation_is_the_only_advanced_flow():
    # Guards the mapping against a later edit quietly promoting a chatty
    # flow onto the expensive model.
    advanced = [
        flow for flow in
        ("scheduler", "interview", "changes", "planner", "learn", "briefing")
        if role_for_flow(flow) == ADVANCED
    ]
    assert advanced == ["scheduler"]


def test_a_call_naming_no_flow_lands_on_default():
    assert role_for_flow("") == DEFAULT


def test_an_unknown_flow_lands_on_default_not_on_fast_or_advanced():
    # A new caller must not silently borrow the cheap or the expensive model.
    assert role_for_flow("something-new") == DEFAULT


# --- role → model ----------------------------------------------------------

def test_a_configured_role_is_used():
    settings = _Settings(llm_model_advanced="big-model")
    assert resolve_model(settings, ADVANCED) == "big-model"


@pytest.mark.parametrize("role", [FAST, DEFAULT, ADVANCED])
def test_an_unset_role_falls_back_to_the_existing_default_model(role):
    assert resolve_model(_Settings(), role) == "base-model"


def test_one_configured_role_does_not_affect_the_others():
    settings = _Settings(llm_model_advanced="big-model")
    assert resolve_model(settings, FAST) == "base-model"
    assert resolve_model(settings, DEFAULT) == "base-model"


def test_settings_predating_roles_still_resolve():
    # An old runtime-settings.json, or any object without the new fields.
    assert resolve_model(_OldSettings(), ADVANCED) == "base-model"


def test_an_explicit_model_overrides_the_role():
    settings = _Settings(llm_model_advanced="big-model")
    assert resolve_model(settings, ADVANCED, "pinned") == "pinned"


def test_an_empty_role_resolves_as_default():
    settings = _Settings(llm_model_default="chat-model")
    assert resolve_model(settings, "") == "chat-model"


# --- role → endpoint -------------------------------------------------------

def test_a_role_can_use_its_own_endpoint():
    settings = _Settings(llm_base_url_advanced="http://advanced/v1")
    assert resolve_base_url(settings, ADVANCED) == "http://advanced/v1"


@pytest.mark.parametrize("role", [FAST, DEFAULT, ADVANCED])
def test_an_unset_role_endpoint_falls_back_to_the_general_one(role):
    assert resolve_base_url(_Settings(), role) == "http://general/v1"


def test_settings_predating_role_endpoints_still_resolve_the_general_one():
    assert resolve_base_url(_OldSettings(), ADVANCED) == "http://general/v1"


# --- the mapping against the real call sites -------------------------------

def test_every_flow_the_backend_actually_passes_is_mapped():
    """Guards the table against the code drifting away from it.

    `role_for_flow` answers DEFAULT for anything unmapped, which is the safe
    behaviour but also a silent one: a new flow would route sensibly and
    nobody would notice it was never considered. Reading the real call sites
    makes adding one a decision rather than an accident.
    """
    import pathlib
    import re

    bl = pathlib.Path(__file__).resolve().parent.parent / "app" / "bl"
    used = set()
    for path in bl.glob("*.py"):
        used.update(re.findall(r'flow="([^"]+)"', path.read_text("utf-8")))

    assert used, "no flow= arguments found — did the call sites move?"
    unmapped = {flow for flow in used if flow not in _MAPPED}
    assert not unmapped, "unmapped flows: %s" % sorted(unmapped)


_MAPPED = {
    "scheduler", "interview", "changes", "planner", "learn", "briefing",
}
