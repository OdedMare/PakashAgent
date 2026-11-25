import { useState } from "react";
import { displayDate } from "../dateFormat";

export function RequestCalendar({ start, end, disabled, onSelect }: {
  start: string;
  end: string;
  disabled: boolean;
  onSelect: (start: string, end: string) => void;
}) {
  const [month, setMonth] = useState(() => {
    const day = start ? new Date(start + "T12:00:00") : new Date();
    return new Date(day.getFullYear(), day.getMonth(), 1);
  });
  const [anchor, setAnchor] = useState("");
  const choosingEnd = Boolean(anchor && anchor === start && !end);
  const year = month.getFullYear();
  const index = month.getMonth();
  const count = new Date(year, index + 1, 0).getDate();
  return (
    <fieldset className="request-calendar" disabled={disabled}>
      <legend>{choosingEnd ? "בחירת היום האחרון (אפשר להשאיר יום יחיד)" : "בחירת יום או תקופה"}</legend>
      <div className="request-month">
        <button type="button" onClick={() => setMonth(new Date(year, index - 1, 1))}>חודש קודם</button>
        <strong>{month.toLocaleDateString("he-IL", { month: "long", year: "numeric" })}</strong>
        <button type="button" onClick={() => setMonth(new Date(year, index + 1, 1))}>חודש הבא</button>
      </div>
      <div className="request-days">
        {Array.from("אבגדהוש", day => <span key={day}>{day}׳</span>)}
        {Array.from({ length: month.getDay() }, (_, i) => <span key={`blank-${i}`} />)}
        {Array.from({ length: count }, (_, i) => {
          const iso = [year, String(index + 1).padStart(2, "0"), String(i + 1).padStart(2, "0")].join("-");
          return <button key={iso} type="button" aria-label={displayDate(iso)}
            aria-pressed={iso >= start && iso <= (end || start)}
            onClick={() => {
              if (choosingEnd) {
                onSelect(iso < anchor ? iso : anchor, iso < anchor ? anchor : iso);
                setAnchor("");
              } else {
                onSelect(iso, "");
                setAnchor(iso);
              }
            }}>{i + 1}</button>;
        })}
      </div>
    </fieldset>
  );
}
