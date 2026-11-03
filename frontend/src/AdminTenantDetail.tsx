import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { adminToken, api } from "./api";
import type { TenantDetail } from "./types";
import { StatusPill, formatDate } from "./ui";

const TIERS = ["TRIAL", "STARTER", "GROWTH", "ENTERPRISE"];

export default function AdminTenantDetail() {
  const { tenantId } = useParams();
  const [tenant, setTenant] = useState<TenantDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const token = adminToken.get();

  async function reload() {
    if (!tenantId) return;
    const data = await api<TenantDetail>(`/platform/tenants/${tenantId}`, { token });
    setTenant(data);
  }

  useEffect(() => {
    reload().catch((err: Error) => setError(err.message));
  }, [tenantId]);

  async function patchTenant(body: Record<string, string>) {
    if (!tenantId) return;
    setError(null);
    try {
      const data = await api<TenantDetail>(`/platform/tenants/${tenantId}`, {
        method: "PATCH",
        token,
        body: JSON.stringify(body),
      });
      setTenant(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }

  async function extendTrial() {
    if (!tenantId) return;
    setError(null);
    try {
      const data = await api<TenantDetail>(
        `/platform/tenants/${tenantId}/extend-trial`,
        { method: "POST", token },
      );
      setTenant(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }

  async function setStatus(path: string, status: string) {
    setError(null);
    try {
      await api(path, {
        method: "PATCH",
        token,
        body: JSON.stringify({ status }),
      });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }

  if (!tenant) return <p>{error ?? "Loading…"}</p>;

  return (
    <>
      <header className="page-head">
        <div>
          <Link className="crumb" to="/admin/tenants">
            Tenants
          </Link>
          <h1>{tenant.name}</h1>
          <p className="muted">
            {tenant.subscription_tier} · trial {formatDate(tenant.trial_ends_at)}
          </p>
        </div>
        <div className="actions">
          <select
            value={tenant.subscription_tier}
            onChange={(e) => patchTenant({ subscription_tier: e.target.value })}
          >
            {TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
          <button type="button" className="ghost" onClick={extendTrial}>
            Extend trial
          </button>
          {tenant.status === "ACTIVE" ? (
            <button
              type="button"
              className="danger"
              onClick={() => patchTenant({ status: "SUSPENDED" })}
            >
              Suspend
            </button>
          ) : (
            <button type="button" onClick={() => patchTenant({ status: "ACTIVE" })}>
              Restore
            </button>
          )}
        </div>
      </header>
      {error ? <p className="error">{error}</p> : null}

      <section className="grid-2">
        <article className="card">
          <h2>Users</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tenant.users.map((user) => (
                <tr key={user.id}>
                  <td>
                    {user.full_name} <StatusPill value={user.status} />
                  </td>
                  <td>{user.email}</td>
                  <td>{user.role}</td>
                  <td>
                    <button
                      type="button"
                      className="tiny"
                      onClick={() =>
                        setStatus(
                          `/platform/users/${user.id}`,
                          user.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
                        )
                      }
                    >
                      {user.status === "ACTIVE" ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
        <article className="card">
          <h2>Companies</h2>
          {tenant.companies.map((company) => (
            <div key={company.id} className="stack">
              <div className="row">
                <strong>{company.name}</strong>
                <StatusPill value={company.status} />
                <button
                  type="button"
                  className="tiny"
                  onClick={() =>
                    setStatus(
                      `/platform/companies/${company.id}`,
                      company.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
                    )
                  }
                >
                  {company.status === "ACTIVE" ? "Disable" : "Enable"}
                </button>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Branch</th>
                    <th>Code</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {(company.branches ?? []).map((branch) => (
                    <tr key={branch.id}>
                      <td>
                        {branch.name} <StatusPill value={branch.status} />
                      </td>
                      <td>{branch.code}</td>
                      <td>
                        <button
                          type="button"
                          className="tiny"
                          onClick={() =>
                            setStatus(
                              `/platform/branches/${branch.id}`,
                              branch.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
                            )
                          }
                        >
                          {branch.status === "ACTIVE" ? "Disable" : "Enable"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </article>
      </section>
    </>
  );
}
