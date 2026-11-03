import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, apiDownload, apiUploadForm } from "../api";
import { useWorkspace } from "../context/WorkspaceContext";
import { Avatar, Card, formatDate, formatDateTime, StatusPill, TableSkeleton } from "../ui";
import { choices, dateField, deadline, Field, PerformanceForm, text, today, Values } from "./PerformanceForm";
import type { Appraisal, Assessment, Goal, Person, Rating } from "./performanceTypes";

import { reviewStatus, reviewTask } from "./performanceTypes";

type Dialog = { title: string; fields: Field[]; initial?: Values; save: (values: Values) => Promise<void>; button?: string };
const goalFields: Field[] = [
  { key: "title", label: "Goal title", required: true }, text("description", "Description"), { key: "category", label: "Category" },
  { key: "measurement", label: "Measurement", type: "select", options: choices("NUMBER", "PERCENTAGE", "CURRENCY", "BOOLEAN", "RATING", "MILESTONE", "QUALITATIVE"), required: true },
  { key: "direction", label: "Direction", type: "select", options: choices("HIGHER_IS_BETTER", "LOWER_IS_BETTER", "TARGET_IS_BEST", "MILESTONE"), required: true },
  { key: "target", label: "Target", type: "number" }, { key: "unit", label: "Unit / currency" },
  { key: "weight", label: "KPI weight (%)", type: "number", min: 0, max: 100, required: true },
  { key: "priority", label: "Priority", type: "select", options: choices("LOW", "NORMAL", "HIGH"), required: true },
  dateField("start_date", "Start date", true), dateField("due_date", "Due date", true),
  { key: "scoring_cap", label: "Achievement at highest rating (%)", type: "number", min: 100, max: 200, required: true, help: "Automatic scoring maps achievement linearly to the configured scale, capped here." },
];

export default function PerformanceAppraisal({ identity, back, changed, section, sectionLinks, returnTo }: { identity: string; back: () => void; changed: () => void; section?: string; sectionLinks?: Record<string, string>; returnTo?: string }) {
  const { user, token, hasPermission: has, notify } = useWorkspace();
  const [record, setRecord] = useState<Appraisal | null>(null);
  const [error, setError] = useState("");
  const [localTab, setTab] = useState("Goals");
  const tab = section ?? localTab;
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [history, setHistory] = useState<Array<{ id: string; created_at: string; details: Record<string, unknown> }> | null>(null);
  const [historyGoal, setHistoryGoal] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Array<{ id: string; filename: string }> | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    let active = true; setError(""); setRecord(null); setDialog(null); setHistory(null); setEvidence(null); setHistoryGoal(null);
    api<Appraisal>(`/performance/appraisals/${identity}`).then(value => { if (active) { setRecord(value); if (has("performance.manage_cycles")) void api<Person[]>(`/performance/people?company_id=${value.cycle.company_id ?? value.company_id}`).then(rows => { if (active) setPeople(rows); }).catch(() => setPeople([])); } }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [identity, revision]);
  const refresh = () => { setRevision(value => value + 1); changed(); };
  async function request(path: string, data: Values, method = "POST", apiBase = "/performance") {
    await api(`${apiBase}/${path}`, { method, body: JSON.stringify(data) });
    refresh(); notify("Performance record saved");
  }
  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  if (error && !record) return <Card title="Appraisal unavailable" padded><p role="alert">{error}</p><button className="btn ghost small" onClick={back} type="button">Back to performance</button></Card>;
  if (!record) return <TableSkeleton rows={5} />;
  const own = record.participant.employee_id === user.employee_id;
  const manager = !own && has("performance.assess_team") && (has("performance.view_all") || [record.participant.manager_id, record.participant.reviewer_id].includes(user.employee_id ?? null));
  const developmentManager = !own && has("performance.manage_development_plans") && (has("performance.view_all") || [record.participant.manager_id, record.participant.reviewer_id].includes(user.employee_id ?? null));
  const editable = !record.finalized_at;
  const goals = record.goals ?? [];
  const activeGoals = goals.filter(goal => goal.status !== "CANCELLED");
  const weight = activeGoals.reduce((sum, goal) => sum + Number(goal.weight), 0);
  const goalWriter = editable && (manager || own && has("performance.manage_own_goals"));
  const entryRoles = record.cycle.config.goal_entry_roles;
  const goalEntry = goalWriter && (!entryRoles ? manager || record.cycle.config.employee_goal_creation : own ? entryRoles.includes("EMPLOYEE") : entryRoles.includes("HR") && has("performance.manage_cycles") || entryRoles.includes("MANAGER") && [record.participant.manager_id, record.participant.reviewer_id].includes(user.employee_id ?? null));
  const prefix = `appraisals/${record.id}`;
  const stageWindow = record.cycle.windows[record.cycle.status];
  const open = (title: string, fields: Field[], save: Dialog["save"], initial?: Values, button?: string) => setDialog({ title, fields, save, initial, button });
  const reasonAction = (goal: Goal, action: string) => open(`${action.replaceAll("-", " ")} goal`, [text("reason", "Reason", action !== "approve")], values => request(`goals/${goal.id}/actions/${action}`, { ...values, version: goal.version, status: "" }));
  const goalForm = (goal?: Goal) => open(goal ? "Revise goal and request fresh approval" : "Create performance goal", [...goalFields, ...(goal ? [text("reason", "Reason for revision", true)] : [])], values => request(goal ? `goals/${goal.id}` : `${prefix}/goals`, { ...values, target: values.target || null, ...(goal ? { version: goal.version } : {}) }, goal ? "PUT" : "POST"), goal ? { ...goal.definition } : { category: "Individual", measurement: "NUMBER", direction: "HIGHER_IS_BETTER", priority: "NORMAL", start_date: record.cycle.start_date, due_date: record.cycle.end_date, weight: 0, scoring_cap: 120 });
  const nextAction = record.status === "GOAL_SETTING" ? "Agree and approve goals (weights must total 100%)." : record.status === "ACTIVE" ? "Record progress and hold check-ins." : record.status === "SELF_ASSESSMENT" ? "Complete and submit employee self-assessment." : record.status === "MANAGER_ASSESSMENT" ? "Assigned manager completes the independent assessment." : record.status === "REVIEW" ? "Hold and record the review meeting." : record.status === "CALIBRATION" ? "HR calibrates the assessment. Employee can acknowledge receipt." : record.status === "FINALIZATION" ? "Complete acknowledgement and finalize the appraisal." : "Appraisal finalized. Follow development actions below.";
  const employeeName = String(record.participant.context.employee_name ?? "Employee");
  const selfWindow = record.cycle.windows.SELF_ASSESSMENT;
  return <section className="performance-appraisal">
    <div className="appraisal-toolbar"><button className="btn ghost small" onClick={back} type="button">← Back to performance</button><div className="actions">{editable && has("performance.manage_cycles") && !record.manager_assessment.submitted_at && <button className="btn ghost small" onClick={() => open("Reassign appraiser", [{ key: "manager_id", label: "Manager", type: "select", options: people.filter(person => person.id !== record.participant.employee_id).map(person => ({ value: person.id, label: person.name })), required: true }, { key: "reviewer_id", label: "Secondary reviewer", type: "select", options: people.filter(person => person.id !== record.participant.employee_id).map(person => ({ value: person.id, label: person.name })) }, text("reason", "Reason for reassignment", true)], values => request(`${prefix}/appraiser`, { ...values, reviewer_id: values.reviewer_id || null, version: record.version }, "PUT"), { manager_id: record.participant.manager_id, reviewer_id: record.participant.reviewer_id })} type="button">Reassign appraiser</button>}</div></div>
    <section className="card appraisal-overview">
      <div className="appraisal-identity"><Avatar name={employeeName} size="lg" /><div><p className="appraisal-eyebrow">Performance review</p><h2>{employeeName}</h2><p className="appraisal-review-name">{record.cycle.name}</p></div><StatusPill value={reviewStatus(record.status)} /></div>
      <dl className="meta-grid appraisal-meta">
        <div><dt>Department</dt><dd>{record.participant.context.department_name || "—"}</dd></div>
        <div><dt>Job title</dt><dd>{record.participant.context.job_title_name || "—"}</dd></div>
        <div><dt>Manager / supervisor</dt><dd>{record.participant.context.manager_name || "Not assigned"}</dd></div>
        <div><dt>Review period</dt><dd>{formatDate(record.cycle.start_date)} – {formatDate(record.cycle.end_date)}</dd></div>
      </dl>
      <div className="appraisal-metrics">
        <div><span>Goal progress</span><strong>{Number(record.goal_progress).toFixed(0)}<small>%</small></strong></div>
        <div><span>Goals completed</span><strong>{record.completed_goals}<small> / {record.goal_count}</small></strong></div>
        <div><span>Goal weights</span><strong>{weight}<small> / 100%</small></strong></div>
        <div><span>{record.scores.final ? "Final score" : "Self-review"}</span><strong className={record.scores.final ? "" : "appraisal-metric-date"}>{record.scores.final ? String(record.scores.final) : selfWindow ? formatDate(selfWindow.start) : "Not scheduled"}</strong><small>{record.scores.final ? String(record.scores.final_rating) : selfWindow ? `Ends ${formatDate(selfWindow.end)}` : "HR will set the dates"}</small></div>
      </div>
      <div className="appraisal-next"><div><strong>{record.finalized_at ? "Review completed" : reviewTask(record.status)}</strong><p>{nextAction}</p></div>{stageWindow && <span>Due {formatDate(stageWindow.end)}</span>}</div>
      {(Boolean(record.scores.recommend_development) || Boolean(record.scores.recommend_pip)) && <p className="appraisal-support">{record.scores.recommend_pip ? "HR may consider an improvement plan after review." : "Development support recommended."}</p>}
    </section>
    {error && <p className="error" role="alert">{error}</p>}
    <nav className="page-tabs" aria-label="Employee review sections">{["Goals", "Check-ins", "Assessment", "Review & decision", "Development", ...(record.events?.length ? ["History"] : [])].map(value => sectionLinks?.[value] ? <Link key={value} to={sectionLinks[value]} state={{ returnTo }} aria-current={tab === value ? "page" : undefined} className={tab === value ? "active" : ""} onClick={() => setDialog(null)}>{value}</Link> : <button key={value} className={tab === value ? "active" : ""} onClick={() => { setTab(value); setDialog(null); }} type="button">{value}</button>)}</nav>
    {dialog && <PerformanceForm key={dialog.title} title={dialog.title} fields={dialog.fields} initial={dialog.initial} submit={dialog.save} close={() => setDialog(null)} button={dialog.button} />}
    {tab === "Goals" && <>
      <Card title="Goals & KPIs" note={`${activeGoals.length} goals · ${record.cycle.config.kpi_weight}% of the overall performance score`} action={goalEntry && record.status === "GOAL_SETTING" ? <button className="btn small" onClick={() => goalForm()} type="button">Add goal</button> : undefined}>
        {!goals.length ? <p className="card-pad">No goals assigned. Add goals during goal setting.</p> : goals.map(goal => <article className="performance-goal" key={goal.id}>
          <div className="performance-goal-head"><h3>{goal.title}</h3><StatusPill value={goal.status} /></div>
          <dl className="appraisal-goal-metrics"><div><dt>Target</dt><dd>{goal.definition.target ?? "Qualitative"} <small>{goal.definition.unit}</small></dd></div><div><dt>Achieved</dt><dd>{goal.actual ?? "—"}</dd></div><div><dt>Weight</dt><dd>{goal.weight}%</dd></div><div><dt>Due date</dt><dd>{formatDate(goal.definition.due_date)}</dd></div></dl>
          <div className="performance-progress-label"><progress aria-label={`${goal.title} progress`} value={Number(goal.progress)} max={100} /><span>{Number(goal.progress).toFixed(0)}% complete</span></div>
          <div className="actions">
            {goalWriter && goal.status === "DRAFT" && <button className="btn small" disabled={busy} onClick={() => void run(() => request(`goals/${goal.id}/actions/submit`, { version: goal.version, status: "" }))} type="button">Submit for approval</button>}
            {editable && manager && goal.status === "PENDING_APPROVAL" && <><button className="btn small" onClick={() => reasonAction(goal, "approve")} type="button">Approve</button><button className="btn ghost small" onClick={() => reasonAction(goal, "request-changes")} type="button">Request changes</button><button className="btn danger small" onClick={() => reasonAction(goal, "reject")} type="button">Reject</button></>}
            {goalWriter && !record.self_assessment.submitted_at && ["APPROVED", "IN_PROGRESS", "COMPLETED"].includes(goal.status) && ["GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT"].includes(record.status) && <>
              <button className="btn small" onClick={() => open("Record goal progress", [{ key: "progress", label: "Progress (%)", type: "number", min: 0, max: 100, required: true }, { key: "actual", label: "Actual achieved", type: "number" }, text("comment", "Progress update", true), text("achievements", "Achievements"), text("blockers", "Blockers")], values => request(`goals/${goal.id}/progress`, { ...values, actual: values.actual || null, version: goal.version }), { progress: goal.progress, actual: goal.actual })} type="button">Update progress</button>
              <label className="btn ghost small performance-upload">Attach evidence<input type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.txt" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void run(async () => { const form = new FormData(); form.append("file", file); await apiUploadForm(`/performance/goals/${goal.id}/evidence`, form, token); refresh(); notify("Evidence uploaded"); }); }} /></label>
            </>}
            <button className="btn ghost small" disabled={busy} onClick={() => void run(async () => { const [updates, files] = await Promise.all([api<Array<{ id: string; created_at: string; details: Record<string, unknown> }>>(`/performance/goals/${goal.id}/progress`), api<Array<{ id: string; filename: string }>>(`/performance/goals/${goal.id}/evidence`)]); setHistory(updates); setEvidence(files); setHistoryGoal(goal.id); })} type="button">View updates & evidence</button>
          </div>
          <details className="appraisal-goal-details"><summary>Goal details & settings</summary><p>{goal.definition.description || "No description provided."}</p><p className="muted">Measurement: {goal.definition.measurement.replaceAll("_", " ").toLowerCase()} · {goal.definition.direction.replaceAll("_", " ").toLowerCase()}</p>{goal.approval.reason && <p>Approval note: {goal.approval.reason}</p>}<div className="actions">{goalEntry && ["GOAL_SETTING", "ACTIVE"].includes(record.status) && goal.status !== "CANCELLED" && <button className="btn ghost small" onClick={() => goalForm(goal)} type="button">Revise</button>}{editable && manager && ["GOAL_SETTING", "ACTIVE"].includes(record.status) && goal.status !== "CANCELLED" && <button className="btn danger small" onClick={() => reasonAction(goal, "cancel")} type="button">Cancel goal</button>}</div></details>
          {historyGoal === goal.id && <section className="appraisal-goal-history"><div className="performance-goal-head"><h4>Updates & evidence</h4><button className="btn ghost small" type="button" onClick={() => setHistoryGoal(null)}>Close</button></div><ol className="appraisal-timeline">{history?.length ? history.map(item => <li key={item.id}><div><strong>{String(item.details.progress)}% progress</strong><time>{formatDateTime(item.created_at)}</time></div><p>{String(item.details.comment ?? "")}</p></li>) : <li>No progress updates yet.</li>}</ol><div className="appraisal-evidence">{evidence?.length ? evidence.map(item => <button className="btn ghost small" key={item.id} onClick={() => void run(() => apiDownload(`/performance/evidence/${item.id}/download`, token, item.filename))} type="button">↓ {item.filename}</button>) : <p>No evidence attached.</p>}</div></section>}
        </article>)}
      </Card>
    </>}
    {tab === "Check-ins" && <Card title="Check-ins" action={goalWriter && ["GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT"].includes(record.status) ? <button className="btn small" onClick={() => open("Record performance check-in", [{ key: "kind", label: "Check-in type", type: "select", options: choices("MONTHLY", "QUARTERLY", "MID_YEAR", "AD_HOC"), required: true }, dateField("meeting_date", "Meeting date", true), dateField("next_review", "Next review"), text("achievements", "Achievements"), text("challenges", "Challenges"), text("employee_comments", "Employee comments"), ...(manager ? [text("manager_feedback", "Manager feedback")] : []), text("agreed_actions", "Agreed actions"), { key: "goal_ids", label: "Related goals", type: "multi", options: activeGoals.map(goal => ({ value: goal.id, label: goal.title })) }], values => request(`${prefix}/check-ins`, { ...values, next_review: values.next_review || null }), { kind: "AD_HOC", meeting_date: today() })} type="button">Add check-in</button> : undefined} padded>
      {record.check_ins?.length ? record.check_ins.map(item => <article key={item.id} className="performance-entry"><h4>{formatDate(item.meeting_date)} · {String(item.details.kind).replaceAll("_", " ")}</h4>{Object.entries(item.details).filter(([key, value]) => value && !["goal_ids", "kind", "meeting_date"].includes(key)).map(([key, value]) => <p key={key}><strong>{key.replaceAll("_", " ")}:</strong> {String(value)}</p>)}</article>) : <p>No check-ins recorded.</p>}
    </Card>}
    {tab === "Assessment" && <AssessmentEditor key={`${record.id}:${record.version}`} record={record} kind={own ? "self" : "manager"} writable={editable && (own ? has("performance.self_assess") && record.status === "SELF_ASSESSMENT" && record.cycle.status === "SELF_ASSESSMENT" : manager && record.cycle.status === "MANAGER_ASSESSMENT" && !record.manager_assessment.submitted_at)} save={(data, submit) => request(`${prefix}/${submit ? `submit-${own ? "self" : "manager"}-assessment` : `${own ? "self" : "manager"}-assessment`}`, { ...data, version: record.version }, submit ? "POST" : "PUT")} />}
    {tab === "Review & decision" && <>
      <Card title="Assessment scores" padded><div className="performance-summary">{Object.entries(record.scores).filter(([key]) => ["kpi", "competency", "pre_calibration", "pre_calibration_rating", "calibrated", "calibrated_rating", "final", "final_rating"].includes(key)).map(([key, value]) => <span key={key}><strong>{key.replaceAll("_", " ")}:</strong> {String(value)}</span>)}</div>{record.scores.calibration_reason && <p>Calibration reason: {String(record.scores.calibration_reason)}</p>}</Card>
      <Card title="Review meeting" padded>{Object.keys(record.review).length ? Object.entries(record.review).filter(([key, value]) => value && key !== "version").map(([key, value]) => <p key={key}><strong>{key.replaceAll("_", " ")}:</strong> {Array.isArray(value) ? value.join(", ") : String(value)}</p>) : <p>No review meeting recorded.</p>}
        {editable && manager && record.status === "REVIEW" && record.cycle.status === "REVIEW" && <button className="btn small" onClick={() => open("Complete appraisal review meeting", [dateField("meeting_date", "Meeting date", true), { key: "attendees", label: "Attendees (one name per line)", type: "textarea" }, text("summary", "Discussion summary", true), text("employee_comments", "Employee comments"), text("manager_comments", "Manager comments"), text("achievements", "Achievements discussed"), text("improvements", "Improvement areas"), text("disagreements", "Disagreements"), text("agreed_actions", "Agreed actions"), dateField("follow_up", "Follow-up date")], values => request(`${prefix}/review`, { ...values, attendees: String(values.attendees).split("\n").map(value => value.trim()).filter(Boolean), follow_up: values.follow_up || null, version: record.version }), { meeting_date: today() })} type="button">Record review meeting</button>}
      </Card>
      <Card title="Employee acknowledgement" note="Acknowledging receipt does not mean agreement." padded>{record.acknowledgement.status ? <><StatusPill value={record.acknowledgement.status} /><p>{record.acknowledgement.comments}</p><p>{formatDateTime(record.acknowledgement.acknowledged_at)}</p></> : <p>Awaiting acknowledgement.</p>}
        {editable && own && ["CALIBRATION", "FINALIZATION"].includes(record.status) && <button className="btn small" onClick={() => open("Acknowledge appraisal receipt", [{ key: "status", label: "Acknowledgement", type: "select", options: choices("ACKNOWLEDGED", "ACKNOWLEDGED_WITH_COMMENTS", "DISAGREES"), required: true }, text("comments", "Comments / disagreement")], values => request(`${prefix}/acknowledge`, { ...values, version: record.version }), { status: "ACKNOWLEDGED" })} type="button">Acknowledge receipt</button>}
      </Card>
      <Card title="Calibration & finalization" padded><div className="actions">
        {editable && has("performance.calibrate") && record.cycle.config.require_calibration && record.cycle.status === "CALIBRATION" && <button className="btn small" onClick={() => open("Calibrate score", [{ key: "score", label: "Calibrated score", type: "number", required: true, min: Number(record.cycle.config.rating_scale.levels[0].minimum), max: Number(record.cycle.config.rating_scale.levels.at(-1)?.maximum) }, text("reason", "Reason (required even if score is unchanged)", true)], values => request(`${prefix}/calibrate`, { ...values, version: record.version }), { score: record.scores.calibrated ?? record.scores.pre_calibration })} type="button">Calibrate appraisal</button>}
        {editable && has("performance.finalize") && record.cycle.status === "FINALIZATION" && <button className="btn small" disabled={busy} onClick={() => open("Finalize appraisal", [], () => request(`${prefix}/finalize`, { version: record.version }), {}, "Finalize and lock record")} type="button">Finalize & lock</button>}
        {has("performance.reopen_appraisal") && !["GOAL_SETTING", "ACTIVE"].includes(record.status) && <button className="btn ghost small" onClick={() => open("Reopen appraisal", [{ key: "stage", label: "Reopen task", type: "select", options: ["GOAL_SETTING", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT", "REVIEW", "FINALIZATION"].map(value => ({ value, label: reviewTask(value) })), required: true }, text("reason", "Reason for reopening", true)], values => request(`${prefix}/reopen`, { ...values, version: record.version }), { stage: "MANAGER_ASSESSMENT" })} type="button">Reopen with reason</button>}
      </div>{record.finalized_at && <p>Finalized {formatDateTime(record.finalized_at)}. Previous finalizations remain in the audit history.</p>}</Card>
    </>}
    {tab === "Development" && <Card title="Development plan" note="Development actions continue after appraisal finalization." action={developmentManager ? <button className="btn small" onClick={() => open("Add development action", [{ key: "title", label: "Title", required: true }, { key: "owner_id", label: "Action owner", type: "select", options: [{ value: record.participant.employee_id, label: String(record.participant.context.employee_name) }, ...(record.participant.manager_id ? [{ value: record.participant.manager_id, label: String(record.participant.context.manager_name) }] : [])], required: true }, dateField("due_date", "Due date", true), text("area", "Development area"), text("skill_gap", "Skill gap"), text("desired_outcome", "Desired outcome"), text("action", "Action", true), { key: "priority", label: "Priority", type: "select", options: choices("LOW", "NORMAL", "HIGH"), required: true }, text("comments", "Comments")], values => request(`${prefix}/development-actions`, values), { owner_id: record.participant.employee_id, priority: "NORMAL" })} type="button">Add action</button> : undefined} padded>
      {record.development_actions?.length ? record.development_actions.map(action => <article key={action.id} className="performance-entry"><h4>{action.title}</h4><StatusPill value={action.status} /><p>{action.details.action}</p><p>{action.details.desired_outcome}</p><p>{action.progress}% · Due {formatDate(action.due_date)} · {deadline(action.due_date)}</p><p>{action.details.comments}</p>{own && has("performance.view_own") && action.owner_id === user.employee_id && !["COMPLETED", "CANCELLED"].includes(action.status) && <button className="btn ghost small" type="button" onClick={() => open("Update my development progress", [{ key: "status", label: "Status", type: "select", options: choices("NOT_STARTED", "IN_PROGRESS", "COMPLETED"), required: true }, { key: "progress", label: "Progress (%)", type: "number", min: 0, max: 100, required: true }, text("comments", "Your update")], values => request(`development-actions/${action.id}`, { ...values, version: action.version }, "PATCH", "/employee-portal"), { status: action.status, progress: action.progress, comments: action.details.employee_comments || "" })}>Update my progress</button>}{action.details.employee_comments && <p>Employee update: {action.details.employee_comments}</p>}{developmentManager && <button className="btn ghost small" onClick={() => open("Update development action", [{ key: "status", label: "Status", type: "select", options: choices("NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED"), required: true }, { key: "progress", label: "Progress (%)", type: "number", min: 0, max: 100, required: true }, text("comments", "Comments")], values => request(`development-actions/${action.id}`, { ...values, version: action.version }, "PATCH"), { status: action.status, progress: action.progress, comments: action.details.comments })} type="button">Update action</button>}</article>) : <p>No development actions recorded.</p>}
    </Card>}
    {tab === "History" && <Card title="Audit & appraisal history" padded>{record.events?.map(item => <details className="performance-entry" key={item.id}><summary>{item.action.replaceAll("_", " ")} · {formatDateTime(item.created_at)}</summary><pre className="performance-audit">{JSON.stringify(item.details, null, 2)}</pre></details>)}</Card>}
  </section>;
}

function AssessmentEditor({ record, kind, writable, save }: { record: Appraisal; kind: "self" | "manager"; writable: boolean; save: (assessment: Assessment, submit: boolean) => Promise<void> }) {
  const source = kind === "self" ? record.self_assessment : record.manager_assessment;
  const other = kind === "self" ? record.manager_assessment : record.self_assessment;
  const [values, setValues] = useState<Assessment>({ ...source, goals: source.goals ?? [], competencies: source.competencies ?? [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function rating(key: "goals" | "competencies", id: string, field: "rating" | "comment", value: string) {
    setValues(current => { const items = [...current[key] ?? []]; const index = items.findIndex(item => item.id === id); const item: Rating = index >= 0 ? { ...items[index] } : { id, rating: "", comment: "" }; item[field] = value; if (index >= 0) items[index] = item; else items.push(item); return { ...current, [key]: items }; });
  }
  async function commit(submit: boolean) {
    setBusy(true); setError("");
    try {
      const { submitted_at: _submitted, ...data } = values;
      const clean: Assessment = { ...data, goals: values.goals?.filter(item => item.rating && record.goals?.some(goal => goal.id === item.id && goal.status !== "CANCELLED")), competencies: values.competencies?.filter(item => item.rating && record.competencies.some(competency => competency.id === item.id)) };
      // Timestamp metadata is server-owned; draft fields are an explicit allowlist.
      await save({ goals: clean.goals, competencies: clean.competencies, summary: clean.summary ?? "", achievements: clean.achievements ?? "", challenges: clean.challenges ?? "", support: clean.support ?? "", career_interests: clean.career_interests ?? "", recommendations: clean.recommendations ?? "" }, submit);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const levels = record.cycle.config.rating_scale.levels;
  const low = Number(levels[0].minimum), high = Number(levels.at(-1)?.maximum);
  return <Card title={kind === "self" ? "Employee self-assessment" : "Manager assessment"} note="Employee and manager ratings are stored separately. Numeric ratings may include decimals within the configured ranges." padded>
    <details className="appraisal-rating-guide"><summary>Rating guide: {low} to {high}</summary><div>{levels.map(level => <p key={level.value}><strong>{level.minimum}–{level.maximum}</strong> {level.label}</p>)}</div></details>
    {source.submitted_at && <p>Submitted {formatDateTime(source.submitted_at)}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <fieldset className="performance-fields" disabled={!writable || busy}>
      {([{ key: "goals" as const, title: "KPIs", items: (record.goals ?? []).filter(goal => goal.status !== "CANCELLED").map(goal => ({ id: goal.id, name: goal.title, description: `${goal.definition.description} · Target ${goal.definition.target ?? "—"}, actual ${goal.actual ?? "—"}, progress ${goal.progress}%, weight ${goal.weight}%` })) }, { key: "competencies" as const, title: "Competencies", items: record.competencies.map(item => ({ id: item.id, name: item.name, description: `${item.description} · ${item.indicators.join("; ")}` })) }]).map(group => <section key={group.key}><h3>{group.title}</h3>{group.items.map(item => {
        const selected = values[group.key]?.find(r => r.id === item.id); const comparison = other[group.key]?.find(r => r.id === item.id);
        return <article className="performance-rating" key={item.id}><div><strong>{item.name}</strong><p>{item.description}</p><p>{kind === "manager" ? "Employee" : "Manager"} rating: {comparison?.rating ?? "Not available"}{comparison?.comment ? ` · ${comparison.comment}` : ""}</p></div>{writable ? <><label>{kind === "self" ? "Employee" : "Manager"} rating<input type="number" min={low} max={high} step="0.01" value={selected?.rating ?? ""} onChange={event => rating(group.key, item.id, "rating", event.target.value)} /></label><label>Comment<textarea value={selected?.comment ?? ""} onChange={event => rating(group.key, item.id, "comment", event.target.value)} /></label></> : <><div><span className="appraisal-readonly-label">{kind === "self" ? "Employee" : "Manager"} rating</span><div className="appraisal-rating-value">{selected?.rating ?? "—"}</div></div><div><span className="appraisal-readonly-label">Comment</span><p className="appraisal-readonly-note">{selected?.comment || "No comment"}</p></div></>}</article>;
      })}</section>)}
      <div className="form-grid">{(["summary", "achievements", "challenges", "support", ...(kind === "self" ? ["career_interests"] : ["recommendations"])] as Array<keyof Assessment>).map(key => <label key={key}>{key.replaceAll("_", " ")}{writable ? <textarea rows={3} value={String(values[key] ?? "")} onChange={event => setValues(current => ({ ...current, [key]: event.target.value }))} /> : <p className="appraisal-readonly-note">{String(values[key] || "Not provided")}</p>}</label>)}</div>
      {writable && <div className="actions"><button className="btn ghost" disabled={busy} onClick={() => void commit(false)} type="button">Save draft</button><button className="btn" disabled={busy} onClick={() => void commit(true)} type="button">Submit {kind === "self" ? "self" : "manager"} assessment</button></div>}
    </fieldset>
    {!writable && <p>This assessment is read-only at the current stage.</p>}
  </Card>;
}
