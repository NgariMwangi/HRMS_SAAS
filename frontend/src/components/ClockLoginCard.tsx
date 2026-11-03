import { FormEvent, useState } from "react";
import { api, apiUrl } from "../api";
import type { Employee } from "../types";

export function ClockLoginCard({
  employee,
  token,
  apiBase = "",
  canManageHr,
  canResetDevice = canManageHr,
  onChanged,
  notify,
}: {
  employee: Employee;
  token: string;
  apiBase?: string;
  canManageHr: boolean;
  canResetDevice?: boolean;
  onChanged: (row: Employee) => void;
  notify: (message: string) => void;
}) {
  const [email, setEmail] = useState(employee.email ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      notify("Clock-in login created.");
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
          <h3>Clock-in login</h3>
          <p>This login is for the employee app. HR still corrects the register on Attendance.</p>
        </div>
      </div>
      <div className="card-pad">
        {employee.clock_login_email ? (
          <>
            <p style={{ margin: 0 }}>{employee.clock_login_email}</p>
            <p className="muted">{employee.has_clock_device ? "A phone is bound to this login." : "No phone bound yet."}</p>
            {canResetDevice && employee.has_clock_device ? (
              <button className="btn ghost small" type="button" disabled={busy} onClick={() => void unlock()}>
                Unlock device
              </button>
            ) : null}
          </>
        ) : canManageHr ? (
          <form className="form-grid" onSubmit={createLogin}>
            <label>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label>Password<input type="password" required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Create login"}</button>
          </form>
        ) : (
          <p className="muted" style={{ margin: 0 }}>No clock-in login yet.</p>
        )}
        {error ? <p className="error">{error}</p> : null}
      </div>
    </section>
  );
}
