import { useCompanyDomain } from "../context/CompanyDomainContext";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, tenantSession, tenantToken } from "../api";
import type { Country, Employee, TenantAuth } from "../types";
import { Skel } from "../ui";
import AuthLayout from "./AuthLayout";
import GoogleSignIn from "../components/GoogleSignIn";

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
    if (mode !== "register" || domainCompany) return;
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
  }, [mode, domainCompany]);

  async function complete(auth: TenantAuth) {
    if (auth.user.role === "EMPLOYEE" && !auth.user.employee_id) {
      throw new Error("Ask HR to link your login to an employee record.");
    }
    tenantToken.set(auth.access_token, auth.refresh_token);
    try {
      const employee = auth.user.role === "EMPLOYEE"
        ? (await api<{ employee: Employee }>("/employee-portal/me", { token: auth.access_token })).employee
        : null;
      tenantSession.set({ tenant: auth.tenant, user: auth.user,
        companyId: employee?.company_id ?? auth.company?.id,
        branchId: employee?.branch_id ?? auth.branch?.id });
      navigate(auth.user.role === "EMPLOYEE" ? "/employee" : "/app", { replace: true });
    } catch (err) {
      tenantToken.clear(); tenantSession.clear(); throw err;
    }
  }

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
      await complete(body);
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
            : "Sign in to your company account. We will open the right portal for your role."}
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
          {error ? <p className="error" role="alert">{error}</p> : null}
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "register" ? "Create workspace" : "Continue"}
          </button>
        </form>
        {mode === "login" && <>
          <div className="portal-divider">or continue with Google</div>
          <GoogleSignIn disabled={submitting} onCredential={async credential => {
            setSubmitting(true); setError(null);
            try {
              await complete(await api<TenantAuth>("/auth/google/login", { method: "POST", credentials: "include",
                body: JSON.stringify({ credential, ...(form.email && form.password ? { email: form.email, password: form.password } : {}) }) }));
            } finally { setSubmitting(false); }
          }} />
          <p className="muted">Employees can use a linked Google account. To link it for the first time, enter your company login email and password above, then select Google.</p>
          <p className="muted">Need an employee account or password reset? Contact your HR administrator.</p>
        </>}
      </div>
      {!domainCompany && <Link className="quiet-link" to="/admin/login">Platform admin</Link>}
    </AuthLayout>
  );
}
