"""צוות אלמוגי: כל האנשים.

  role       התפקיד
  cycle      מבנה היציאות: 11/3, 10/4 או 1 ל־3
  group      הקבוצה בתוך מבנה היציאות
  status     סדיר / קצין / נחפף
  can_train  מוסמך/ת לחפוף

כולם מותרים בכל המשמרות, ואף אחד לא מוסמך כמפקד/ת משמרת.
"""

P = dict

ROSTER = [
    # ---------- מב"ר סדיר ----------
    P(name="חני", role='מב"ר', cycle="10/4", group="א", status="סדיר", can_train=True),
    P(name="יערה", role='מב"ר', cycle="10/4", group="א", status="סדיר", can_train=False),
    P(name="אלון", role='מב"ר', cycle="11/3", group="א", status="סדיר", can_train=True),
    P(name="עינב", role='מב"ר', cycle="10/4", group="ב", status="סדיר", can_train=True),
    P(name="מאיה", role='מב"ר', cycle="10/4", group="ב", status="סדיר", can_train=True),
    P(name="לוטם", role='מב"ר', cycle="10/4", group="ב", status="סדיר", can_train=True),
    # ---------- נחפפים ----------
    P(name="אלה", role='מב"ר', cycle="11/3", group="ב", status="נחפף", can_train=False),
    P(name="נדב", role='מב"ר', cycle="11/3", group="ב", status="נחפף", can_train=False),
    # ---------- קצינים ----------
    P(name="שקד חדד", role='קב"ר', cycle="1 ל־3", group="א", status="קצין", can_train=True),
    P(name="נטע חטיאל", role='קב"ר', cycle="1 ל־3", group="ב", status="קצין", can_train=True),
    P(name="אורי", role='קב"ר', cycle="1 ל־3", group="ג", status="קצין", can_train=True),
]
