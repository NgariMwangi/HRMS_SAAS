import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { adminSession, adminToken, api } from "../api";
import { IconPeople } from "../components/icons";
import type { Overview, Tenant } from "../types";
import { Card, EmptyState, Kpi, KpiRowSkeleton, PersonCell, Skel, StatusPill, TableSkeleton } from "../ui";

function greeting(name: string): string {
  const hour = new Date().getHours();
  const first = name.split(" ")[0];
  if (hour < 12) return `Good morning, ${first}`;
  if (hour < 17) return `Good afternoon, ${first}`;
  return `Good evening, ${first}`;
}

export default function AdminOverview() {
  const navigate = useNavigate();
  const token = adminToken.get();
  const admin = adminSession.get();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      navigate("/admin/login");
      return;
    }
    Promise.all([
      api<Overview>("/platform/overview", { token }),
      api<Tenant[]>("/platform/tenants", { token }),
    ])
      .then(([stats, rows]) => {
        setOverview(stats);
        setTenants(rows.slice(0, 6));
      })
      .catch((err: Error) => {
        setError(err.message);
        adminToken.clear();
        navigate("/admin/login");
      })
      .finally(() => setLoading(false));
  }, [navigate, token]);

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{greeting(admin?.full_name ?? "there")}</h1>
          <p>{today} · Platform console. Here is what is happening across every tenant.</p>
        </div>
        <div className="actions">
          <Link className="btn ghost small" to="/admin/countries">Countries</Link>
          <Link className="btn small" to="/admin/tenants">View tenants</Link>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {loading ? (
        <>
          <KpiRowSkeleton />
          <div className="grid-2">
            <section className="card"><TableSkeleton rows={5} cols={3} /></section>
            <section className="card card-pad">
              <div className="meta-grid">
                {Array.from({ length: 4 }, (_, index) => (
                  <div key={index}>
                    <Skel w={72} h={10} />
                    <div style={{ marginTop: 8 }}><Skel w="60%" h={16} /></div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : (
      <>
      <div className="kpis">
        <Kpi label="Tenants" value={overview?.tenant_count ?? "—"} icon={<IconPeople />} />
        <Kpi label="Active" value={overview?.active_tenant_count ?? "—"} hint="Live workspaces" />
        <Kpi label="Trials" value={overview?.trial_count ?? "—"} />
        <Kpi label="Companies" value={overview?.company_count ?? "—"} hint={`${overview?.user_count ?? 0} users`} />
      </div>
      <div className="grid-2">
        <Card title="Recent tenants" action={<Link className="btn ghost small" to="/admin/tenants">View all</Link>}>
          {tenants.length === 0 ? (
            <EmptyState title="No tenants yet" note="New trials will show up here." />
          ) : (
            <table>
              <thead><tr><th>Workspace</th><th>Plan</th><th>Status</th></tr></thead>
              <tbody>
                {tenants.map((tenant) => (
                  <tr key={tenant.id}>
                    <td data-label="Workspace">
                      <Link className="row-link" to={`/admin/tenants/${tenant.id}`}>
                        <PersonCell name={tenant.name} email={`${tenant.company_count ?? 0} companies`} />
                      </Link>
                    </td>
                    <td data-label="Plan"><StatusPill value={tenant.subscription_tier} /></td>
                    <td data-label="Status"><StatusPill value={tenant.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Platform snapshot" padded>
          <dl className="meta-grid">
            <div><dt>Users</dt><dd>{overview?.user_count ?? "—"}</dd></div>
            <div><dt>Companies</dt><dd>{overview?.company_count ?? "—"}</dd></div>
            <div><dt>Branches</dt><dd>{overview?.branch_count ?? "—"}</dd></div>
            <div><dt>Trials</dt><dd>{overview?.trial_count ?? "—"}</dd></div>
          </dl>
        </Card>
      </div>
      </>
      )}
    </>
  );
}
