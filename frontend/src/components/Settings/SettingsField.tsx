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
        // API keys are credentials for a service, not the manager's login
        // password. Password managers otherwise offer (and sometimes inject)
        // the password used on the workspace screen into this field.
        autoComplete={secret ? "new-password" : "off"}
        data-1p-ignore={secret ? "true" : undefined}
        data-lpignore={secret ? "true" : undefined}
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

/** A closed set of choices, where a free-text field would let the boss save a
 *  value the backend rejects.
 *
 *  `hint` renders under the control rather than beside the label, because the
 *  thing worth saying about a choice is what picking it *does* — and that is a
 *  sentence, not a parenthetical. */
export function SettingsSelect({
  settings,
  name,
  label,
  options,
  hint,
}: {
  settings: SettingsController;
  name: string;
  label: string;
  options: { value: string; label: string }[];
  hint?: string;
}) {
  const current = settings.text(name);
  return (
    <>
      <label className="field-label" htmlFor={`set-${name}`}>
        {label}
      </label>
      <select
        id={`set-${name}`}
        className="settings-input"
        dir="auto"
        // An unknown stored value (an older save, a hand-edited file) would
        // otherwise render as a blank control that silently rewrites the
        // setting on the next save. Falling back to the first option shows
        // what will actually be used.
        value={options.some((item) => item.value === current) ? current : options[0]?.value ?? ""}
        onChange={(event) => settings.set(name, event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <p className="settings-hint">{hint}</p> : null}
    </>
  );
}

/** An emptied number field sends `null`, not `""` — the backend treats null as
 *  "leave it alone" and would reject an empty string as a bad int. */
function inputValue(value: string, type?: string) {
  if (type !== "number") return value;
  return value === "" ? null : Number(value);
}
