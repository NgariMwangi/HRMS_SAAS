import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, tenantSession, tenantToken } from "../api";
import type { TenantAuth, Employee } from "../types";
import AuthLayout from "./AuthLayout";
import GoogleSignIn from "../components/GoogleSignIn";

export default function EmployeeLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function complete(auth: TenantAuth) {
    if (!auth.user.employee_id) throw new Error("Ask HR to link your login to an employee record.");
    tenantToken.set(auth.access_token, auth.refresh_token);
    try {
      const me = await api<{ employee: Employee }>("/employee-portal/me");
      tenantSession.set({ tenant: auth.tenant, user: auth.user, companyId: me.employee.company_id, branchId: me.employee.branch_id });
      navigate("/employee", { replace: true });
    } catch (err) { tenantToken.clear(); tenantSession.clear(); throw err; }
  }
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await complete(await api<TenantAuth>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <AuthLayout kicker="Your working day, all in one place">
    <div className="panel employee-login"><div className="eyebrow">EMPLOYEE PORTAL</div><h1>Welcome back</h1>
      <p className="muted">Use the account provided by your HR team.</p>
      <form onSubmit={login}>
        <label>Work login email<input type="email" autoComplete="username" required value={email} onChange={event => setEmail(event.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" required maxLength={72} value={password} onChange={event => setPassword(event.target.value)} /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form><div className="portal-divider">or continue with Google</div>
      <GoogleSignIn disabled={busy} onCredential={async credential => { setError(""); await complete(await api<TenantAuth>("/auth/google/login", { method: "POST", credentials: "include", body: JSON.stringify({ credential, ...(email && password ? { email, password } : {}) }) })); }} />
      <p className="muted">First time using Google? Enter your work login email and password above, then select Google to link your account.</p>
      <p className="muted">Need an account or password reset? Contact your HR administrator.</p>
    </div><Link className="quiet-link" to="/">HR workspace sign in</Link>
  </AuthLayout>;
}
