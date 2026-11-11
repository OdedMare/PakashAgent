"""A repeated correction, worded and keyed for the preferences table.

Pure functions over one entry of `observe_corrections()["repeated"]`. No
model: the background path writes these sentences unattended, so they claim
nothing beyond what was counted.
"""

from typing import Dict, List

from app.bl.schedule_service.rows import text


def pattern_key(entry: dict) -> str:
    """The identity of a counted pattern: this person, shift and weekday.

    Stored in `subject` and used to deduplicate, so the same pattern seen
    again is recognised as the same observation however it ends up worded.
    """
    parts = [
        text(entry.get("employee")),
        text(entry.get("shift")),
        text(entry.get("weekday")),
    ]
    if not parts[0]:
        return ""
    return "|".join(parts)


def pattern_sentence(entry: dict) -> str:
    """The counted pattern as a sentence, with no model involved.

    Deliberately flat: it describes what was counted and claims nothing
    beyond it. When `learn_from_changes` does run, the model's wording
    replaces this.
    """
    employee = text(entry.get("employee"))
    where = " ".join(
        part for part in (text(entry.get("shift")), text(entry.get("weekday")))
        if part
    )
    if where:
        return "נראה ש%s לא משובץ/ת ל%s" % (employee, where)
    return "נראה שיש תיקונים חוזרים בשיבוץ של %s" % employee


def pattern_evidence(entry: dict) -> str:
    """The count and the manager's own reasons, verbatim.

    Never a paraphrase: a checkable claim is what makes a suggestion
    something the manager can meaningfully approve (D21).
    """
    said = [text(reason) for reason in entry.get("reasons") or []]
    said = [reason for reason in said if reason]
    evidence = "תוקן %d פעמים" % (entry.get("count") or 0)
    seen = " ".join(
        part for part in (
            text(entry.get("first_seen")), text(entry.get("last_seen"))
        ) if part
    )
    if seen:
        evidence += " (%s)" % seen.replace(" ", " – ")
    if said:
        evidence += ", מהנימוקים שנרשמו: " + "; ".join(said[:3])
    return evidence


def worded_by_subject(
    rules: List[dict], repeated: List[dict]
) -> Dict[str, str]:
    """Match the model's candidate sentences back onto counted patterns.

    Matched by the person's name appearing in the rule's text, which is loose
    on purpose. A miss costs nothing -- the pattern is still recorded with its
    counted sentence -- while a strict join would need the model to echo a key
    back, and a model asked to carry an identifier is given a way to get one
    wrong.
    """
    worded: Dict[str, str] = {}
    for entry in repeated:
        employee = text(entry.get("employee"))
        subject = pattern_key(entry)
        if not subject or not employee:
            continue
        for rule in rules or []:
            sentence = text(rule.get("text"))
            if sentence and employee in sentence:
                worded[subject] = sentence
                break
    return worded
