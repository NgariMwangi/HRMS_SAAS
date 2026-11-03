import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, tenantToken } from "./api";
import type { Country, TenantAuth } from "./types";

const emptyForm = {
  owner_full_name: "",
  email: "",
  password: "",
  tenant_name: "",
  company_name: "",
  country_id: "",
};

export default function TenantAuth() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"register" | "login">("login");
  const [countries, setCountries] = useState<Country[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (tenantToken.get()) navigate("/workspace", { replace: true });
  }, [navigate]);

  useEffect(() => {
    api<Country[]>("/countries")
      .then(setCountries)
      .catch((err: Error) => setError(err.message));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body =
        mode === "register"
          ? form
          : { email: form.email, password: form.password };
      const result = await api<TenantAuth>(
        mode === "register" ? "/auth/register" : "/auth/login",
        { method: "POST", body: JSON.stringify(body) },
      );
      tenantToken.set(result.access_token);
      navigate("/workspace");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="split">
      <section className="split-brand">
        <p className="eyebrow">HRMS</p>
        <h1>People operations for East Africa.</h1>
        <p>
          One workspace for your group, then companies and branches in Kenya,
          Uganda, Tanzania, and Rwanda.
        </p>
      </section>
      <section className="split-panel">
        <div className="auth-card">
          <div className="tabs">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
            >
              Start a trial
            </button>
          </div>
          <form onSubmit={onSubmit}>
            {mode === "register" ? (
              <>
                <label>
                  Your name
                  <input
                    required
                    value={form.owner_full_name}
                    onChange={(e) =>
                      setForm({ ...form, owner_full_name: e.target.value })
                    }
                  />
                </label>
                <label>
                  Workspace
                  <input
                    required
                    value={form.tenant_name}
                    onChange={(e) =>
                      setForm({ ...form, tenant_name: e.target.value })
                    }
                  />
                </label>
                <label>
                  First company
                  <input
                    required
                    value={form.company_name}
                    onChange={(e) =>
                      setForm({ ...form, company_name: e.target.value })
                    }
                  />
                </label>
                <label>
                  Country
                  <select
                    required
                    value={form.country_id}
                    onChange={(e) =>
                      setForm({ ...form, country_id: e.target.value })
                    }
                  >
                    <option value="">Select country</option>
                    {countries.map((country) => (
                      <option key={country.id} value={country.id}>
                        {country.name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : null}
            <label>
              Email
              <input
                required
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </label>
            {error ? <p className="error">{error}</p> : null}
            <button type="submit" disabled={submitting}>
              {submitting
                ? "Please wait…"
                : mode === "register"
                  ? "Create workspace"
                  : "Continue"}
            </button>
          </form>
          <p className="fineprint">
            Platform owner? <Link to="/admin/login">Open console</Link>
          </p>
        </div>
      </section>
    </div>
  );
}
