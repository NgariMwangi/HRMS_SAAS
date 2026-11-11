import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { Card, EmptyState, Kpi, KpiRowSkeleton, StatusPill } from "../../ui";
import "./dashboard.css";

type Person = { employee_id: string; name: string; company_id: string; company: string; branch: string };
type Alert = Person & { date: string; days: number };
type Run = { id: string; company_id: string; branch_id: string; company: string; branch: string; currency: string; status: string; employees: number; gross: string; deductions: string; net: string };
type Summary = {
  as_of: string; month: string; scope: string; companies: number; branches: number; employees: number | null;
  pending: { leave: number | null; payroll: number | null; overtime: number | null };
  on_leave: (Person & { leave_type: string; end_on: string; return_on: string | null; portion: string | null })[] | null;
  alerts: { birthdays: Alert[]; probation: Alert[] } | null;
  contracts: Alert[] | null;
  missing: (Person & { missing: string[] })[] | null;
  payroll: Run[] | null;
  activity: { at: string; title: string; company_id: string; company: string; href: string }[];
};

const dateLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const timing = (days: number) => days === 0 ? "Today" : days === 1 ? "Tomorrow" : days < 0 ? `${Math.abs(days)} days overdue` : `In ${days} days`;
const money = (value: string, currency: string) => `${currency} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function List({ children, empty, count }: { children: ReactNode; empty: string; count: number }) {
  return count ? <ul className="dash-list dashboard-scroll">{children}</ul> : <EmptyState title={empty} note="For the selected view." />;
}

export default function Dashboard() {
  const { token, user, company, companies, setCompanyId, setBranchId, hasPermission } = useWorkspace();
  const [all, setAll] = useState(false);
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const canAll = user.role === "OWNER" && companies.length > 1;
  const workspace = all && canAll;
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    if (!company) { setLoading(false); return; }
    setLoading(true);
    const query = new URLSearchParams();
    if (!workspace) query.set("company_id", company.id);
    api<Summary>(`/employees/dashboard?${query}`, { token })
      .then(result => { if (active) setData(result); })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company?.id, token, workspace, retry]);

  function contextLink(companyId: string, branchId?: string) { if (companyId !== company?.id) setCompanyId(companyId); if (branchId) setBranchId(branchId); }
  const person = (row: Person) => <div className="dashboard-person"><Link to={hasPermission("people.view_all") || hasPermission("people.manage") || hasPermission("people.view_team") ? `/app/people/${row.employee_id}` : "/app/leave"} onClick={() => contextLink(row.company_id)}><strong>{row.name}</strong></Link><span className="muted">{[workspace ? row.company : "", row.branch].filter(Boolean).join(" · ")}</span></div>;
  const alertList = (rows: Alert[], empty: string, review = false) => <List count={rows.length} empty={empty}>{rows.map(row => <li className="dash-row" key={row.employee_id}>
    <div>{person(row)}<span className="muted">{dateLabel(row.date)}{review && row.days <= 0 ? " · Review needed" : ""}</span></div>
    <span className={`pill ${row.days <= 0 ? "pill-pending" : ""}`}>{timing(row.days)}</span>
  </li>)}</List>;
  const approvals = data ? [
    { label: "Leave requests", count: data.pending.leave, href: "/app/leave", note: "Awaiting your review" },
    { label: "Payroll runs", count: data.pending.payroll, href: "/app/payroll", note: "Draft runs to review" },
    { label: "Overtime requests", count: data.pending.overtime, href: "/app/payroll/overtime", note: "Pending approval" },
  ].filter(row => row.count !== null) : [];
  const pendingCount = approvals.reduce((sum, row) => sum + (row.count ?? 0), 0);
  const month = data?.month ?? "";

  return <div className="dash-page dashboard-page">
    <div className="page-head">
      <div><h1>{new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 17 ? "Good afternoon" : "Good evening"}, {user.full_name.split(" ")[0]}</h1>
        <p>{workspace ? "Your workspace at a glance" : `${company?.name ?? "Workspace"} at a glance`}{data ? ` · ${dateLabel(data.as_of)}` : ""}</p></div>
      <div className="actions dash-actions">{hasPermission("people.manage") && <Link className="btn small" to="/app/people/new">Add employee</Link>}
        <button className="btn ghost small" type="button" disabled={loading} onClick={() => setRetry(value => value + 1)}>Refresh</button></div>
    </div>
    <div className="dashboard-toolbar">
      <label>View<select value={workspace ? "all" : company?.id ?? ""} onChange={event => { if (event.target.value === "all") setAll(true); else { setAll(false); setCompanyId(event.target.value); } }}>
        {canAll && <option value="all">All companies</option>}{companies.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select></label>
      <p className="muted">Alerts and leave use today’s date. Payroll shows the latest available payroll month.</p>
    </div>
    {loading ? <div aria-busy="true"><KpiRowSkeleton count={4} className="kpis dash-kpis" /><p className="muted" role="status">Loading your dashboard…</p></div>
      : error ? <section className="card card-pad"><p className="error" role="alert">Could not load the dashboard: {error}</p><button className="btn" onClick={() => setRetry(value => value + 1)}>Try again</button></section>
        : !data ? <EmptyState title="Select a company to get started" note="Choose a company from your workspace." /> : <>
          <div className="kpis dash-kpis">
            <Kpi label="Companies" value={data.companies} hint={workspace ? "In this workspace" : "Selected company"} />
            <Kpi label="Branches" value={data.branches} hint="In this view" />
            {data.employees !== null && <Kpi label="Employees" value={data.employees} hint="Active and suspended" />}
            {approvals.length > 0 && <Kpi label="Pending approvals" value={pendingCount} hint="Across all months" />}
          </div>
          {approvals.length > 0 && <Card title="Needs your attention" note="Open requests and payroll runs across all months">
            <div className="dashboard-approvals">{approvals.map(row => <div className="dashboard-approval" key={row.label}>
              <span className="muted">{row.label}</span><strong>{row.count}</strong><span>{row.note}</span>
              {!workspace && <Link className="btn ghost small" to={row.href}>Review</Link>}
            </div>)}</div>{workspace && <p className="muted dashboard-note">Choose a company above to review its approvals.</p>}
          </Card>}
          <div className="dashboard-columns">
            {data.on_leave !== null && <Card title="Who’s on leave today" note={`${data.on_leave.length} approved ${data.on_leave.length === 1 ? "absence" : "absences"}`}>
              <List count={data.on_leave.length} empty="Nobody is on approved leave today">{data.on_leave.map(row => <li className="dash-row" key={`${row.employee_id}-${row.end_on}`}>
                <div>{person(row)}<span className="muted">{row.leave_type} · {row.portion ? `${Number(row.portion) === 0.5 ? "Half" : "Quarter"} day — today` : `Expected back ${row.return_on ? dateLabel(row.return_on) : dateLabel(row.end_on)}`}</span></div>
                <span className="pill pill-approved">{row.portion ? "Partial day" : "On leave"}</span>
              </li>)}</List>
            </Card>}
            {data.alerts && <Card title="Birthday alerts" note="Today and the next 14 days">{alertList(data.alerts.birthdays, "No birthdays in the next 14 days")}</Card>}
            {data.alerts && <Card title="Probation reviews" note="Overdue, due today, or ending within 14 days">{alertList(data.alerts.probation, "No probation reviews due or coming up", true)}</Card>}
            {data.contracts !== null && <Card title="Contract expiry alerts" note="Expired or ending within 60 days">{alertList(data.contracts, "No contracts expiring within 60 days", true)}</Card>}
          </div>
          {data.payroll !== null && <Card title="Payroll overview" note={new Date(`${month}-01T12:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" })} action={!workspace ? <Link className="btn ghost small" to={`/app/payroll?month=${month}`}>Open payroll</Link> : undefined}>
            {data.payroll.length === 0 ? <EmptyState title="No payroll has been run yet" note="Open payroll to prepare the first run." /> : <div className="table-scroll dashboard-payroll"><table><thead><tr><th>Company / Branch</th><th>Status</th><th>Employees</th><th>Gross pay</th><th>Deductions</th><th>Net pay</th></tr></thead><tbody>
              {data.payroll.map(run => <tr key={run.id}><td><Link to={`/app/payroll?month=${month}`} onClick={() => contextLink(run.company_id, run.branch_id)}><strong>{run.branch}</strong></Link><div className="muted">{run.company}</div></td><td><StatusPill value={run.status} /></td><td>{run.employees}</td><td>{money(run.gross, run.currency)}</td><td>{money(run.deductions, run.currency)}</td><td><strong>{money(run.net, run.currency)}</strong></td></tr>)}
            </tbody></table></div>}
          </Card>}
          <div className="dashboard-columns">
            {data.missing !== null && <Card title="Missing employee information" note={`${data.missing.length} ${data.missing.length === 1 ? "employee needs" : "employees need"} attention · Current records`}>
              <List count={data.missing.length} empty="Employee information is complete">{data.missing.map(row => <li className="dash-row" key={row.employee_id}><div>{person(row)}<div className="dashboard-tags">{row.missing.map(label => <span className="pill pill-pending" key={label}>{label}</span>)}</div></div><Link className="btn ghost small" to={`/app/people/${row.employee_id}`} onClick={() => contextLink(row.company_id)}>View</Link></li>)}</List>
            </Card>}
            <Card title="Recent activity" note="Latest employee changes, leave decisions, and payroll approvals you can view">
              <List count={data.activity.length} empty="No recent activity to display">{data.activity.map((row, index) => <li className="dash-row" key={`${row.at}-${index}`}><div><Link to={row.href} onClick={() => contextLink(row.company_id)}><strong>{row.title}</strong></Link><div className="muted">{row.company} · {new Date(row.at.endsWith("Z") || /[+-]\d\d:\d\d$/.test(row.at) ? row.at : `${row.at}Z`).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div></div></li>)}</List>
            </Card>
          </div>
          {hasPermission("organization.manage") && <div className="actions"><Link className="btn ghost small" to="/app/companies">Manage companies</Link><Link className="btn ghost small" to="/app/branches">Manage branches</Link></div>}
        </>}
  </div>;
}
