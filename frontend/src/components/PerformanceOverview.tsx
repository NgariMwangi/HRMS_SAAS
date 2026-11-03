import { Link } from "react-router-dom";
import { Card, Kpi, StatusPill, formatDate } from "../ui";
import { performancePages } from "../performanceNavigation";
import { useWorkspace } from "../context/WorkspaceContext";
import { Appraisal, Cycle, Notice, Report, reviewStatus, reviewTask } from "./performanceTypes";

export default function PerformanceOverview({ reviews, records, notices, report }: { reviews: Cycle[]; records: Appraisal[]; notices: Notice[]; report: Report | null }) {
  const { hasPermission: has, user } = useWorkspace();
  const active = reviews.filter(item => item.status !== "COMPLETED" && item.status !== "DRAFT");
  const pending = records.filter(item => !item.finalized_at);
  const links = performancePages.filter(page => ["reviews", "team", "my", "reports", "improvement-plans"].includes(page.path)
    && (page.path !== "my" || user.employee_id) && (!page.permissions.length || page.permissions.some(has)));
  return <>
    <div className="kpis performance-kpis"><Kpi label="Reviews in progress" value={active.length} /><Kpi label="Employees in review" value={report?.participants ?? records.length} /><Kpi label="Completed assessments" value={report?.finalized ?? records.filter(item => item.finalized_at).length} /><Kpi label="Unread updates" value={notices.filter(item => !item.read_at).length} /></div>
    <div className="performance-shortcuts">{links.map(page => <Link key={page.path} className="card performance-shortcut" to={`/app/performance/${page.path}`}><strong>{page.label}<span aria-hidden="true">→</span></strong><p>{page.description}</p></Link>)}</div>
    <div className="performance-columns">
      <Card title="Current reviews" note="Review periods that are currently in progress." padded>{active.length ? active.map(item => <div className="performance-overview-row" key={item.id}><div><strong>{item.name}</strong><p>{formatDate(item.start_date)} – {formatDate(item.end_date)}</p><small>{reviewTask(item.status)}</small></div><StatusPill value={reviewStatus(item.status)} /></div>) : <p className="muted">No reviews are currently in progress.</p>}</Card>
      <Card title="Next tasks" note="Open an employee review to continue." padded>{pending.slice(0, 5).map(item => <Link className="performance-task" key={item.id} to={`/app/performance/appraisals/${item.id}/${item.status === "SELF_ASSESSMENT" || item.status === "MANAGER_ASSESSMENT" ? "assessment" : item.status === "ACTIVE" || item.status === "GOAL_SETTING" ? "goals" : "results"}`} state={{ returnTo: "/app/performance/overview" }}><strong>{item.participant.context.employee_name}</strong><span>{reviewTask(item.status)}</span></Link>)}{!pending.length && <p className="muted">You're up to date. New assignments will appear here.</p>}</Card>
    </div>
  </>;
}
