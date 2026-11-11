import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api, tenantToken } from "../api";
import type { Branch, Company, User } from "../types";
import { EmptyState, StatusPill } from "../ui";
import AppShell from "./AppShell";

export default function TenantWorkspace() {
  const navigate = useNavigate();
  const token = tenantToken.get();
  const [user, setUser] = useState<User | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      navigate("/");
      return;
    }
    Promise.all([
      api<User>("/auth/me", { token }),
      api<Company[]>("/companies", { token }),
      api<Branch[]>("/branches", { token }),
    ])
      .then(([me, companyRows, branchRows]) => {
        setUser(me);
        setCompanies(companyRows);
        setBranches(branchRows);
      })
      .catch((err: Error) => {
        setError(err.message);
        if (err.message.includes("authenticated") || err.message.includes("token")) {
          tenantToken.clear();
          navigate("/");
        }
      });
  }, [navigate, token]);

  function signOut() {
    tenantToken.clear();
    navigate("/");
  }

  return (
    <AppShell
      brandLabel="Workspace"
      onSignOut={signOut}
      nav={<NavLink to="/workspace">Home</NavLink>}
    >
        <div className="page-head">
          <div>
            <div className="eyebrow">Organisation</div>
            <div className="title-row">
              <h1>{user?.full_name ?? "Workspace"}</h1>
              {user ? <StatusPill value={user.role} /> : null}
            </div>
            <p>{user?.email}</p>
          </div>
        </div>
        {error ? <p className="error">{error}</p> : null}
        <div className="stats">
          <div className="stat"><span>Companies</span><strong>{companies.length}</strong></div>
          <div className="stat"><span>Branches</span><strong>{branches.length}</strong></div>
          <div className="stat"><span>Role</span><strong>{user?.role ?? "—"}</strong></div>
          <div className="stat"><span>Status</span><strong>{user?.status ?? "—"}</strong></div>
        </div>
        <section className="card">
          <div className="card-head"><h3>Companies</h3></div>
          {companies.length === 0 ? (
            <EmptyState title="No companies" note="Your first company appears here after signup." />
          ) : (
          <table>
            <thead><tr><th>Name</th><th>Status</th></tr></thead>
            <tbody>
              {companies.map((company) => (
                <tr key={company.id}>
                  <td>{company.name}</td>
                  <td><StatusPill value={company.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          )}
        </section>
        <section className="card">
          <div className="card-head"><h3>Branches</h3></div>
          {branches.length === 0 ? (
            <EmptyState title="No branches" note="Head office and other sites will list here." />
          ) : (
          <table>
            <thead><tr><th>Name</th><th>Status</th></tr></thead>
            <tbody>
              {branches.map((branch) => (
                <tr key={branch.id}>
                  <td>{branch.name}</td>
                  <td><StatusPill value={branch.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          )}
        </section>
    </AppShell>
  );
}
