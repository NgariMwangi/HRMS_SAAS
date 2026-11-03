import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { adminToken, api } from "../api";
import type { Tenant } from "../types";
import { EmptyState, matchesSearch, PageHeader, PersonCell, SearchField, StatusPill, TableSkeleton, formatDate } from "../ui";

export default function AdminTenants() {
  const navigate = useNavigate();
  const token = adminToken.get();
  const [params] = useSearchParams();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setQuery(params.get("q") ?? "");
  }, [params]);

  useEffect(() => {
    if (!token) {
      navigate("/admin/login");
      return;
    }
    api<Tenant[]>("/platform/tenants", { token })
      .then(setTenants)
      .catch(() => {
        adminToken.clear();
        navigate("/admin/login");
      })
      .finally(() => setLoading(false));
  }, [navigate, token]);

  const filtered = useMemo(() => {
    return tenants.filter((tenant) => (
      matchesSearch(query, tenant.name) &&
      (!status || tenant.status === status) &&
      (!plan || tenant.subscription_tier === plan)
    ));
  }, [query, tenants, status, plan]);

  return (
    <>
      <PageHeader
        title="Tenants"
        description="Every subscription owner on the platform."
      />
      <div className="filters">
        <SearchField value={query} onChange={setQuery} placeholder="Search by name" />
        <select value={plan} onChange={(event) => setPlan(event.target.value)}>
          <option value="">All plans</option>
          <option>TRIAL</option>
          <option>STARTER</option>
          <option>GROWTH</option>
          <option>ENTERPRISE</option>
        </select>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All statuses</option>
          <option>ACTIVE</option>
          <option>SUSPENDED</option>
        </select>
      </div>
      <section className="card">
        {loading ? (
          <TableSkeleton rows={7} cols={7} />
        ) : (
        <>
        <table>
          <thead>
            <tr>
              <th>Workspace</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Companies</th>
              <th>Users</th>
              <th>Trial ends</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((tenant) => (
              <tr key={tenant.id}>
                <td data-label="Workspace"><PersonCell name={tenant.name} /></td>
                <td data-label="Plan"><StatusPill value={tenant.subscription_tier} /></td>
                <td data-label="Status"><StatusPill value={tenant.status} /></td>
                <td className="numeric" data-label="Companies">{tenant.company_count ?? 0}</td>
                <td className="numeric" data-label="Users">{tenant.user_count ?? 0}</td>
                <td data-label="Trial ends">{formatDate(tenant.trial_ends_at)}</td>
                <td><Link className="row-link" to={`/admin/tenants/${tenant.id}`}>View</Link></td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <EmptyState title="Nothing to show" note={query ? "No tenant matches that search." : "No tenants have signed up yet."} />
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        <div className="paginate">
          <span>{filtered.length} workspaces</span>
          <span>Page 1 of 1</span>
        </div>
        </>
        )}
      </section>
    </>
  );
}
