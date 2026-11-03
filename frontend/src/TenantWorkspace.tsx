import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, tenantToken } from "./api";
import type { Branch, Company, User } from "./types";
import { StatusPill } from "./ui";

export default function TenantWorkspace() {
  const navigate = useNavigate();
  const token = tenantToken.get();
  const [user, setUser] = useState<User | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      navigate("/", { replace: true });
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
        tenantToken.clear();
        setError(err.message);
        navigate("/", { replace: true });
      });
  }, [navigate, token]);

  if (!user) return <div className="page-loading">Loading workspace…</div>;

  return (
    <div className="workspace">
      <header className="topbar">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{user.full_name}</h1>
        </div>
        <button
          className="ghost"
          type="button"
          onClick={() => {
            tenantToken.clear();
            navigate("/");
          }}
        >
          Sign out
        </button>
      </header>
      {error ? <p className="error">{error}</p> : null}
      <section className="grid-2">
        <article className="card">
          <h2>Companies</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((company) => (
                <tr key={company.id}>
                  <td>{company.name}</td>
                  <td>
                    <StatusPill value={company.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
        <article className="card">
          <h2>Branches</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Code</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {branches.map((branch) => (
                <tr key={branch.id}>
                  <td>{branch.name}</td>
                  <td>{branch.code}</td>
                  <td>
                    <StatusPill value={branch.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      </section>
    </div>
  );
}
