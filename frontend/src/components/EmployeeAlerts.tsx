import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "../context/WorkspaceContext";
import { Card, EmptyState } from "../ui";

type Alert = { employee_id: string; name: string; branch_id: string; date: string; days: number };
type Alerts = { as_of: string; window_days: number; birthdays: Alert[]; probation: Alert[] };

function timing(days: number): string {
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 0) return `${Math.abs(days)} ${days === -1 ? "day" : "days"} overdue`;
  return `In ${days} days`;
}

export function EmployeeAlerts() {
  const { company, token, allBranches, hasPermission } = useWorkspace();
  const allowed = hasPermission("people.view_all") || hasPermission("people.manage");
  const [data, setData] = useState<Alerts | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    if (!company || !allowed) return;
    setLoading(true);
    api<Alerts>(`/employees/alerts?company_id=${company.id}`, { token })
      .then(result => { if (active) setData(result); })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company?.id, token, allowed, retry]);

  if (!allowed || !company) return null;
  const sections = [
    { title: "Birthday alerts", rows: data?.birthdays ?? [], note: "Today and the next 14 days", empty: "No birthdays in the next 14 days" },
    { title: "Probation alerts", rows: data?.probation ?? [], note: "Due for review or ending within 14 days", empty: "No probation reviews due or coming up" },
  ];
  return <div className="grid-2">
    {sections.map(section => <Card key={section.title} title={section.title} note={`${company.name} · ${section.note}`}>
      {loading ? <p className="muted" role="status" style={{ padding: 16 }}>Loading alerts…</p>
        : error ? <div style={{ padding: 16 }}><p className="error" role="alert">Could not load alerts: {error}</p><button type="button" className="btn ghost small" onClick={() => setRetry(value => value + 1)}>Try again</button></div>
          : section.rows.length === 0 ? <EmptyState title={section.empty} note="Alerts use active employees with a recorded date." />
            : <ul className="dash-list" style={{ maxHeight: 360, overflowY: "auto" }}>
              {section.rows.map(row => <li className="dash-row" key={row.employee_id}>
                <div><Link to={`/app/people/${row.employee_id}`}><strong>{row.name}</strong></Link>
                  <div className="muted">{new Date(`${row.date}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}{allBranches.find(branch => branch.id === row.branch_id)?.name ? ` · ${allBranches.find(branch => branch.id === row.branch_id)?.name}` : ""}</div>
                </div>
                <span className={row.days <= 0 ? "pill pill-pending" : "pill"}>{timing(row.days)}{section.title === "Probation alerts" && row.days <= 0 ? " · Review needed" : ""}</span>
              </li>)}
            </ul>}
    </Card>)}
  </div>;
}
