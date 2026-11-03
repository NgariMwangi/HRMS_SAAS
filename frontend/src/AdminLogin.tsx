import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { adminToken, api } from "./api";
import type { PlatformAuth } from "./types";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("owner@hrms.local");
  const [password, setPassword] = useState("ChangeMe123!");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await api<PlatformAuth>("/platform/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      adminToken.set(result.access_token);
      navigate("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="split split-admin">
      <section className="split-brand">
        <p className="eyebrow">Platform</p>
        <h1>Control every tenant from one console.</h1>
        <p>Plans, access, companies, branches, and country reference data.</p>
      </section>
      <section className="split-panel">
        <div className="auth-card">
          <h2>Owner sign in</h2>
          <form onSubmit={onSubmit}>
            <label>
              Email
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error ? <p className="error">{error}</p> : null}
            <button type="submit" disabled={submitting}>
              {submitting ? "Please wait…" : "Enter console"}
            </button>
          </form>
          <p className="fineprint">
            Tenant workspace? <Link to="/">Go back</Link>
          </p>
        </div>
      </section>
    </div>
  );
}
