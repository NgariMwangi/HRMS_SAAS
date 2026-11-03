import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Card, formatDate, StatusPill } from "../ui";
import type { Appraisal } from "./performanceTypes";
import type { SimpleAppraisal } from "./appraisalTypes";
import { statusLabel } from "./appraisalTypes";
import { useWorkspace } from "../context/WorkspaceContext";

export default function PerformanceHistory({ companyId, employeeId }: { companyId: string; employeeId: string }) {
  const [rows, setRows] = useState<Appraisal[]>([]);
  const [current, setCurrent] = useState<SimpleAppraisal[]>([]);
  const { user, hasPermission: has } = useWorkspace();
  const scope = user.employee_id === employeeId && has("performance.view_own") ? "my" : has("performance.view_all") || has("performance.manage_cycles") ? "manage" : "team";
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true; setRows([]); setError("");
    api<Appraisal[]>(`/performance/appraisals?company_id=${companyId}&employee_id=${employeeId}`).then(value => { if (active) setRows(value); }).catch((err: Error) => { if (active) setError(err.message); });
    api<SimpleAppraisal[]>(`/performance/simple/records?company_id=${companyId}&employee_id=${employeeId}&scope=${scope}`).then(value => { if (active) setCurrent(value); }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [companyId, employeeId, scope]);
  return <Card title="Performance history" note="Each appraisal preserves its original department, job title and appraiser." padded>
    {current.map(item => <article key={item.id}><Link to={`/app/performance/records/${item.id}`}>{item.review.name}</Link> <StatusPill value={statusLabel[item.status]} /><p>{item.result.score || "Pending"} · {item.result.rating || "Result not published"} · {item.context.manager_name}</p></article>)}
    {error ? <p role="alert">{error}</p> : rows.length ? rows.map(item => <article key={item.id}><Link to={`/app/performance/appraisals/${item.id}/results`}>{item.cycle.name} (archive)</Link> <StatusPill value={item.status} /><p>{String(item.scores.final ?? "—")} · {String(item.scores.final_rating ?? "Pending")} · {item.participant.context.department_name || "No department"} · {item.participant.context.manager_name} · {formatDate(item.finalized_at)}</p></article>) : !current.length && <p>No performance history available.</p>}
  </Card>;
}
