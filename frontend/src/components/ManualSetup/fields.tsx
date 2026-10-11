/** The labelled input and the pill checkbox group every setup section shares. */

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="manual-field"><span>{label}</span>{children}</label>;
}

export function CheckboxGrid({ label, values, selected, onChange }: { label: string; values: string[]; selected: string[]; onChange: (value: string[]) => void }) {
  return <fieldset className="manual-checkboxes"><legend>{label}</legend>{values.map((value) => <label key={value}><input type="checkbox" checked={selected.includes(value)} onChange={(event) => onChange(event.target.checked ? [...selected, value] : selected.filter((item) => item !== value))} /><span>{value}</span></label>)}</fieldset>;
}
