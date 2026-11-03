import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminToken, api } from "./api";
import type { Tenant } from "./types";
import { StatusPill, formatDate } from "./ui";

export default function AdminTenants() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Tenant[]>("/platform/tenants", { token: adminToken.get() })
      .then(setTenants)
      .catch((err: Error) => setError(err.message));
  }, []);

  const filtered = tenants.filter((tenant) =>
    tenant.name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Tenants</p>
          <h1>Workspaces</h1>
        </div>
        <input
          className="search"
          placeholder="Search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </header>
      {error ? <p className="error">{error}</p> : null}
      <article className="card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Companies</th>
              <th>Users</th>
              <th>Trial ends</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((tenant) => (
              <tr key={tenant.id}>
                <td>
                  <Link to={`/admin/tenants/${tenant.id}`}>{tenant.name}</Link>
                </td>
                <td>{tenant.subscription_tier}</td>
                <td>
                  <StatusPill value={tenant.status} />
                </td>
                <td>{tenant.company_count ?? 0}</td>
                <td>{tenant.user_count ?? 0}</td>
                <td>{formatDate(tenant.trial_ends_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </>
  );
}
