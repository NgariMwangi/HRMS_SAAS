import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { adminToken, adminSession, api } from "../api";
import type { PlatformAuth } from "../types";
import AuthLayout from "./AuthLayout";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("owner@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body = await api<PlatformAuth>("/platform/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      adminToken.set(body.access_token, body.refresh_token);
      adminSession.set(body.admin);
      navigate("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout kicker="Operate every tenant from one calm console">
      <div className="panel">
        <h2>Admin sign in</h2>
        <p className="lede">Manage every tenant from one console.</p>
        <form onSubmit={onSubmit}>
          <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} /></label>
          {error ? <p className="error">{error}</p> : null}
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : "Continue"}
          </button>
        </form>
      </div>
      <Link className="quiet-link" to="/">Back to customer login</Link>
    </AuthLayout>
  );
}
