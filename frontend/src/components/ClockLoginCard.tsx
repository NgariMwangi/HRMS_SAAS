import { FormEvent, useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import type { Employee } from "../types";

export function ClockLoginCard({
  employee,
  token,
  apiBase = "",
  canManageHr,
  canEditLogin = false,
  canResetDevice = canManageHr,
  onChanged,
  notify,
}: {
  employee: Employee;
  token: string;
  apiBase?: string;
  canManageHr: boolean;
  canEditLogin?: boolean;
  canResetDevice?: boolean;
  onChanged: (row: Employee) => void;
  notify: (message: string) => void;
}) {
  const [email, setEmail] = useState(employee.clock_login_email ?? employee.email ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  useEffect(() => {
    setEmail(employee.clock_login_email ?? employee.email ?? "");
    setPassword(""); setConfirmation(""); setEditing(false); setError(null);
  }, [employee.id, employee.clock_login_email, employee.email]);

  async function saveLogin(event: FormEvent) {
    event.preventDefault();
    if (!canEditLogin) return;
    setError(null);
    if (password !== confirmation) { setError("New passwords do not match."); return; }
    setBusy(true);
    try {
      await api(`/employees/${employee.id}/login`, { method: "PATCH", token, body: JSON.stringify({ email: email.trim(), ...(password ? { password } : {}) }) });
      onChanged(await api<Employee>(`/employees/${employee.id}`, { token }));
      setPassword(""); setConfirmation(""); setEditing(false);
      notify("Employee login updated.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update login"); }
    finally { setBusy(false); }
  }

  async function createLogin(event: FormEvent) {
    event.preventDefault();
    if (!canManageHr) return;
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/employees/${employee.id}/login`), {
        method: "POST",
        token,
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const refreshed = await api<Employee>(apiUrl(apiBase, `/employees/${employee.id}`), { token });
      onChanged(refreshed);
      setPassword("");
      notify("Employee login created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create login");
    } finally {
      setBusy(false);
    }
  }

  async function unlock() {
    if (!canResetDevice) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<Employee>(apiUrl(apiBase, `/employees/${employee.id}/clock-device/reset`), {
        method: "POST",
        token,
      });
      onChanged(saved);
      notify("Device unlocked. They can clock in from a new phone.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unlock device");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h3>Employee portal login</h3>
          <p>Sign-in details for the employee portal and attendance clock-in.</p>
        </div>
      </div>
      <div className="card-pad">
        {employee.clock_login_email ? (
          <>
            <p style={{ margin: 0 }}>{employee.clock_login_email}</p>
            <p className="muted">{employee.has_clock_device ? "A phone is bound to this login." : "No phone bound yet."}</p>
            {canEditLogin && !editing && <button className="btn ghost small" type="button" disabled={busy} onClick={() => { setEmail(employee.clock_login_email ?? ""); setEditing(true); setError(null); }}>Change login / reset password</button>}
            {canEditLogin && editing && <form onSubmit={saveLogin}><fieldset disabled={busy}><div className="form-grid">
              <label>Login email<input type="email" autoComplete="off" required value={email} onChange={e => setEmail(e.target.value)} /></label>
              <label>New password (optional)<input type="password" autoComplete="new-password" minLength={8} maxLength={72} value={password} onChange={e => setPassword(e.target.value)} /></label>
              <label>Confirm new password<input type="password" autoComplete="new-password" required={Boolean(password)} maxLength={72} value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
            </div><p className="muted">Leave both password fields blank to keep the existing password. This changes sign-in details, not the employee's work or personal email.</p><div className="actions"><button className="btn" type="submit">Save login</button><button className="btn ghost" type="button" onClick={() => { setEditing(false); setPassword(""); setConfirmation(""); setError(null); }}>Cancel</button></div></fieldset></form>}
            {canResetDevice && employee.has_clock_device ? (
              <button className="btn ghost small" type="button" disabled={busy} onClick={() => void unlock()}>
                Unlock device
              </button>
            ) : null}
          </>
        ) : canManageHr ? (
          <form className="form-grid" onSubmit={createLogin}>
            <label>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label>Password<input type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Create login"}</button>
          </form>
        ) : (
          <p className="muted" style={{ margin: 0 }}>No employee portal login yet.</p>
        )}
        {error ? <p className="error">{error}</p> : null}
      </div>
    </section>
  );
}
