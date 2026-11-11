import { useEffect, useState, type FormEvent } from "react";
import { api, apiUrl } from "../api";

type Settings = { bank_name: string | null; bank_branch: string | null; bank_account_number: string | null; bank_code: string | null; swift_code: string | null; prorate_payroll: boolean };
const fields = [["bank_name", "Bank name"], ["bank_branch", "Bank branch"], ["bank_account_number", "Account number"], ["bank_code", "Bank code"], ["swift_code", "SWIFT code"]] as const;

export function EmployeePaySettings({ token, apiBase = "", employeeId, notify }: { token: string; apiBase?: string; employeeId: string; notify: (message: string) => void }) {
  const [form, setForm] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const endpoint = apiUrl(apiBase, `/employees/${employeeId}/pay-settings`);
  useEffect(() => {
    let active = true;
    setForm(null); setError(null);
    api<Settings>(endpoint, { token }).then(row => { if (active) setForm(row); }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [endpoint, token]);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { setForm(await api<Settings>(endpoint, { token, method: "PATCH", body: JSON.stringify(form) })); notify("Bank details and payroll settings saved."); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <section className="card"><div className="card-head"><div><h3>Bank details and payroll settings</h3><p>Payment account and salary proration for this employee.</p></div></div>
    <div className="card-pad">{error ? <p role="alert" className="error">{error}</p> : null}
      {form ? <form onSubmit={save}><fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}><div className="form-grid">{fields.map(([key, label]) => <label key={key}>{label}<input value={form[key] ?? ""} maxLength={key === "bank_account_number" ? 50 : key === "bank_code" || key === "swift_code" ? 20 : 100} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}</div>
        <label className="check"><input type="checkbox" checked={form.prorate_payroll} onChange={event => setForm({ ...form, prorate_payroll: event.target.checked })} /> Prorate salary when joining during the payroll period</label>
        <p className="muted">Uses calendar days employed / 30. Turn off to pay the full monthly salary. Future joining dates remain excluded.</p>
        <button className="btn primary" disabled={busy}>{busy ? "Saving..." : "Save bank and payroll settings"}</button></fieldset></form> : !error ? <p>Loading bank details...</p> : null}
    </div></section>;
}
