"""Strict structured outputs: the strict form, and the reply read back."""

from app.bl.chat_schema import CHAT_SCHEMA
from app.bl.directive_agent.schema import TURN_SCHEMA
from app.dal.llm.ladder import attempts
from app.dal.llm.strict_schema import drop_nulls, to_strict

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["reply"],
    "properties": {
        "reply": {"type": "string"},
        "kind": {"type": "string", "enum": ["a", "b"]},
        "rows": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name"],
            "properties": {"name": {"type": "string"}, "note": {"type": "string"}},
        }},
    },
}


def test_every_property_is_required_and_the_optional_ones_may_be_null():
    strict = to_strict(SCHEMA)

    assert strict["required"] == ["reply", "kind", "rows"]
    assert strict["properties"]["kind"] == {"type": ["string", "null"], "enum": ["a", "b", None]}
    assert strict["properties"]["rows"]["items"]["required"] == ["name", "note"]
    assert SCHEMA["required"] == ["reply"]  # The caller's schema is not touched.


def test_a_free_form_object_has_no_strict_form():
    loose = dict(SCHEMA, properties=dict(SCHEMA["properties"], extra={"type": "object"}))

    assert to_strict(loose) is None
    assert to_strict(dict(SCHEMA, additionalProperties=True)) is None


def test_the_nulls_strict_mode_adds_are_taken_back_out():
    reply = {"reply": "שלום", "kind": None, "rows": [{"name": "דנה", "note": None}]}

    assert drop_nulls(reply, SCHEMA) == {"reply": "שלום", "rows": [{"name": "דנה"}]}
    assert drop_nulls({"reply": None}, SCHEMA) == {"reply": None}  # Required stays.


def test_the_ladder_starts_with_the_strict_rung_and_keeps_the_rest():
    rungs = attempts([{"role": "user", "content": "x"}], None, SCHEMA)

    assert rungs[0]["response_format"]["json_schema"]["strict"] is True
    assert "strict" not in rungs[1]["response_format"]["json_schema"]
    assert len(rungs) == 5
    assert len(attempts([], None, {"type": "object"})) == 4


def test_the_agent_schemas_have_a_strict_form():
    assert to_strict(CHAT_SCHEMA) is not None
    assert to_strict(TURN_SCHEMA) is not None
