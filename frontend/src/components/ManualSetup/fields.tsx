/** The labelled input every setup section shares. */

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="manual-field"><span>{label}</span>{children}</label>;
}
