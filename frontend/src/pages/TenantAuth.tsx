import { useCompanyDomain } from "../context/CompanyDomainContext";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, tenantSession, tenantToken } from "../api";
import type { Country, TenantAuth } from "../types";
import { Skel } from "../ui";
import AuthLayout from "./AuthLayout";

const empty = {
  owner_full_name: "",
  email: "",
  password: "",
  tenant_name: "",
  company_name: "",
  country_id: "",
};

export default function TenantAuth() {
  const { company: domainCompany } = useCompanyDomain();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"register" | "login">("login");
  const [countries, setCountries] = useState<Country[]>([]);
  const [form, setForm] = useState(empty);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (tenantToken.get()) navigate(tenantSession.get()?.user.role === "EMPLOYEE" ? "/employee" : "/app", { replace: true });
  }, [navigate]);

  useEffect(() => {
    let cancelled = false;
    async function load(attempt = 0) {
      try {
        const rows = await api<Country[]>("/countries");
        if (!cancelled) {
          setCountries(rows);
          setError(null);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        if (attempt < 8) {
          window.setTimeout(() => load(attempt + 1), Math.min(4000, 400 * (attempt + 1)));
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load countries");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body =
        mode === "register"
          ? await api<TenantAuth>("/auth/register", { method: "POST", body: JSON.stringify(form) })
          : await api<TenantAuth>("/auth/login", {
              method: "POST",
              body: JSON.stringify({ email: form.email, password: form.password }),
            });
      tenantToken.set(body.access_token, body.refresh_token);
      tenantSession.set({
        tenant: body.tenant,
        user: body.user,
        companyId: body.company?.id,
        branchId: body.branch?.id,
      });
      navigate(body.user.role === "EMPLOYEE" ? "/employee" : "/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }

  function bind(name: keyof typeof empty) {
    return {
      value: form[name],
      onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
        setForm((current) => ({ ...current, [name]: event.target.value })),
    };
  }

  return (
    <AuthLayout>
      <div className="panel">
        <h2>{mode === "register" ? "Create your workspace" : "Sign in"}</h2>
        <p className="lede">
          {mode === "register"
            ? "14-day trial. First company and branch included."
            : "Access your HRMS workspace."}
        </p>
        <div className="tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Sign in
          </button>
          {!domainCompany && <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Start trial
          </button>}
        </div>
        <form onSubmit={onSubmit}>
          {mode === "register" ? (
            <>
              <div className="form-grid">
                <label>Your name<input required autoComplete="name" {...bind("owner_full_name")} /></label>
                <label>Workspace<input required {...bind("tenant_name")} /></label>
              </div>
              <div className="form-grid">
                <label>Company<input required {...bind("company_name")} /></label>
                <label>
                  Country
                  {countries.length === 0 ? (
                    <Skel w="100%" h={40} />
                  ) : (
                    <select required {...bind("country_id")}>
                      <option value="">Select</option>
                      {countries.map((country) => (
                        <option key={country.id} value={country.id}>{country.name}</option>
                      ))}
                    </select>
                  )}
                </label>
              </div>
            </>
          ) : null}
          <label>Email<input required type="email" autoComplete="email" {...bind("email")} /></label>
          <label>
            Password
            <input required type="password" minLength={8} autoComplete={mode === "register" ? "new-password" : "current-password"} {...bind("password")} />
          </label>
          {error ? <p className="error">{error}</p> : null}
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "register" ? "Create workspace" : "Continue"}
          </button>
        </form>
      </div>
      {!domainCompany && <Link className="quiet-link" to="/admin/login">Platform admin</Link>}
      <Link className="quiet-link" to="/employee/login">Employee portal</Link>
    </AuthLayout>
  );
}
