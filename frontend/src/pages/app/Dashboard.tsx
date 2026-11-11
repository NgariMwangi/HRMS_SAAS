import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { IconPlus } from "../../components/icons";
import { EmployeeAlerts } from "../../components/EmployeeAlerts";
import type { Employee } from "../../types";
import { Card, EmptyState, Kpi, KpiRowSkeleton, PersonCell, StatusPill } from "../../ui";

function DashListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <ul className="dash-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className="dash-row">
          <div className="person">
            <span className="skel skel-avatar" style={{ width: 36, height: 36 }} />
            <div>
              <span className="skel" style={{ width: index % 2 ? 132 : 168, height: 12 }} />
              <span className="skel" style={{ width: 72, height: 10, marginTop: 8 }} />
            </div>
          </div>
          <span className="skel skel-pill" style={{ width: 58, height: 22 }} />
        </li>
      ))}
    </ul>
  );
}

function greeting(name: string): string {
  const hour = new Date().getHours();
  const first = name.split(" ")[0];
  if (hour < 12) return `Good morning, ${first}`;
  if (hour < 17) return `Good afternoon, ${first}`;
  return `Good evening, ${first}`;
}

export default function Dashboard() {
  const { token, user, company, branch, companies, allBranches, hasPermission } = useWorkspace();
  const [employeeCount, setEmployeeCount] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!company) {
      setEmployeeCount(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<Employee[]>(`/employees?company_id=${company.id}`, { token })
      .then((rows) => setEmployeeCount(rows.length))
      .catch(() => setEmployeeCount(0))
      .finally(() => setLoading(false));
  }, [company?.id, token]);

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="dash-page">
      <div className="page-head">
        <div>
          <h1>{greeting(user.full_name)}</h1>
          <p>
            {today}
            {company ? ` · ${company.name}` : ""}
            {branch ? ` · ${branch.name}` : ""}
          </p>
        </div>
        <div className="actions dash-actions">
          {hasPermission("organization.manage") ? <><Link className="btn ghost small" to="/app/companies">Companies</Link><Link className="btn ghost small" to="/app/branches">Branches</Link></> : null}
          {hasPermission("people.manage") ? <Link className="btn small" to="/app/people/new"><IconPlus /> Add employee</Link> : null}
        </div>
      </div>

      {loading ? (
        <>
          <KpiRowSkeleton count={4} className="kpis dash-kpis" />
          <div className="grid-2">
            <section className="card">
              <div className="card-head"><div><h3>Companies</h3></div></div>
              <DashListSkeleton />
            </section>
            <section className="card">
              <div className="card-head"><div><h3>Branches</h3></div></div>
              <DashListSkeleton />
            </section>
          </div>
        </>
      ) : (
        <>
          <div className="kpis dash-kpis">
            <Kpi label="Companies" value={companies.length} hint="In this workspace" />
            <Kpi label="Branches" value={allBranches.length} hint="In this workspace" />
            <Kpi label="Employees" value={employeeCount} hint={company ? company.name : "Select a company"} />
            <Kpi label="Pending approvals" value={0} hint="Leave and payroll" />
          </div>

          <EmployeeAlerts />

          <div className="grid-2">
            <Card
              title="Companies"
              note={companies.length === 1 ? "1 company" : `${companies.length} companies`}
              action={hasPermission("organization.manage") ? <Link className="btn ghost small" to="/app/companies">Manage</Link> : null}
            >
              {companies.length === 0 ? (
                <EmptyState title="No companies" note="Your first company is created at signup." />
              ) : (
                <ul className="dash-list">
                  {companies.map((row) => (
                    <li key={row.id} className={row.id === company?.id ? "dash-row is-current" : "dash-row"}>
                      <PersonCell
                        name={row.name}
                        email={row.legal_name && row.legal_name !== row.name ? row.legal_name : undefined}
                      />
                      <StatusPill value={row.status} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card
              title="Branches"
              note={allBranches.length === 1 ? "1 branch" : `${allBranches.length} branches`}
              action={hasPermission("organization.manage") ? <Link className="btn ghost small" to="/app/branches">Manage</Link> : null}
            >
              {allBranches.length === 0 ? (
                <EmptyState title="No branches" note="Head office is created at signup." />
              ) : (
                <ul className="dash-list">
                  {allBranches.map((row) => {
                    const owner = companies.find((item) => item.id === row.company_id);
                    return (
                      <li key={row.id} className={row.id === branch?.id ? "dash-row is-current" : "dash-row"}>
                        <PersonCell
                          name={row.name}
                          email={owner?.name}
                        />
                        <StatusPill value={row.status} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
