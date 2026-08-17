import type { SettingsController } from "./useSettings";

type FieldProps = {
  type?: string;
  optional?: string;
  placeholder?: string;
  /** Force `dir="auto"` for a field that may hold Hebrew. Connection strings,
   *  URLs, and keys are Latin-script data and stay LTR inside the RTL page. */
  rtl?: boolean;
  list?: string;
  min?: string;
  max?: string;
  step?: string;
};

export function SettingsField({
  settings,
  name,
  label,
  ...props
}: FieldProps & {
  settings: SettingsController;
  name: string;
  label: string;
}) {
  const secret = props.type === "password";
  const saved = secret && settings.secretSaved(name);
  return (
    <>
      <label className="field-label" htmlFor={`set-${name}`}>
        {label}
        {props.optional ? <span className="optional"> ({props.optional})</span> : null}
        {saved ? <span className="key-hint"> (נשמר)</span> : null}
      </label>
      <input
        id={`set-${name}`}
        className="settings-input"
        type={props.type ?? "text"}
        dir={props.rtl ? "auto" : "ltr"}
        list={props.list}
        min={props.min}
        max={props.max}
        step={props.step}
        // A stored secret renders as an empty field, never as the mask: the
        // mask is a protocol value, and showing it invites the boss to edit
        // asterisks into a new key.
        placeholder={saved ? "השאירו ריק כדי לשמור את הערך הנוכחי" : props.placeholder}
        value={saved ? "" : settings.text(name)}
        onChange={(event) =>
          settings.set(name, inputValue(event.target.value, props.type))
        }
      />
    </>
  );
}

export function SettingsToggle({
  settings,
  name,
  label,
  optional,
}: {
  settings: SettingsController;
  name: string;
  label: string;
  optional?: string;
}) {
  return (
    <label className="field-label">
      <input
        type="checkbox"
        checked={settings.checked(name)}
        onChange={(event) => settings.set(name, event.target.checked)}
      />
      {label}
      {optional ? <span className="optional"> ({optional})</span> : null}
    </label>
  );
}

/** An emptied number field sends `null`, not `""` — the backend treats null as
 *  "leave it alone" and would reject an empty string as a bad int. */
function inputValue(value: string, type?: string) {
  if (type !== "number") return value;
  return value === "" ? null : Number(value);
}
