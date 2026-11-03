import { FormEvent, useState } from "react";
import type { AppraisalPerson, AppraisalTemplate, Criterion, Review, SimpleAppraisal } from "./appraisalTypes";
import { newCriterion, starterCriteria } from "./appraisalTypes";

export function CriteriaEditor({ value, onChange, weighted }: { value: Criterion[]; onChange: (value: Criterion[]) => void; weighted: boolean }) {
  const patch = (id: string, data: Partial<Criterion>) => onChange(value.map(c => c.id === id ? { ...c, ...data } : c));
  const weight = value.filter(c => c.section === "OBJECTIVE").reduce((sum, c) => sum + Number(c.weight || 0), 0);
  return <div className="ap-criteria-editor">
    <p className="muted">Use responsibilities and objectives already communicated to the employee. Explain what success looks like.</p>
    {value.map((c, index) => <fieldset className="ap-criterion" key={c.id}><legend>{c.section === "OBJECTIVE" ? "Objective" : "Working behaviour"} {index + 1}</legend><div className="form-grid">
      <label>Title<input required maxLength={200} value={c.title} onChange={e => patch(c.id, { title: e.target.value })} /></label>
      <label>Section<select value={c.section} onChange={e => patch(c.id, { section: e.target.value as Criterion["section"] })}><option value="OBJECTIVE">Work results / individual objective</option><option value="BEHAVIOUR">Working behaviour</option></select></label>
      <label className="span-2">Expected result or standard<textarea required maxLength={2000} rows={2} value={c.expected} onChange={e => patch(c.id, { expected: e.target.value })} /></label>
      <label>How achievement will be checked<textarea rows={2} maxLength={2000} value={c.evidence} onChange={e => patch(c.id, { evidence: e.target.value })} /></label>
      <label>Due date (optional)<input type="date" value={c.due_date || ""} onChange={e => patch(c.id, { due_date: e.target.value || null })} /></label>
      {weighted && c.section === "OBJECTIVE" && <label>Objective weight (%)<input type="number" required min={0.01} max={100} step="0.01" value={c.weight} onChange={e => patch(c.id, { weight: e.target.value })} /></label>}
    </div><button type="button" className="btn ghost small" disabled={value.length === 1} onClick={() => onChange(value.filter(item => item.id !== c.id))}>Remove criterion</button></fieldset>)}
    <div className="actions"><button type="button" className="btn ghost small" disabled={value.length >= 50} onClick={() => onChange([...value, newCriterion()])}>+ Add individual objective</button><button type="button" className="btn ghost small" disabled={value.length >= 50} onClick={() => onChange([...value, newCriterion("BEHAVIOUR")])}>+ Add working behaviour</button>{weighted && <strong className={weight !== 100 ? "error" : ""}>Objective weights: {weight} / 100%</strong>}</div>
  </div>;
}

export function TemplateEditor({ value, save, cancel, busy }: { value?: AppraisalTemplate; save: (data: unknown) => Promise<void>; cancel: () => void; busy: boolean }) {
  const [name, setName] = useState(value?.name || "");
  const [weighted, setWeighted] = useState(value?.weighted || false);
  const [criteria, setCriteria] = useState<Criterion[]>(value?.criteria || starterCriteria());
  return <form className="card card-pad ap-form" onSubmit={e => { e.preventDefault(); void save({ name, weighted, criteria, version: value?.version }); }}><h2>{value ? "Edit template" : "Create appraisal template"}</h2><p>Templates provide a starting point. Each employee's form can be tailored before publication; existing reviews keep their original template.</p>
    <label>Template name<input required maxLength={160} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Sales staff appraisal" /></label>
    <label className="ap-check"><input type="checkbox" checked={weighted} onChange={e => setWeighted(e.target.checked)} />Use weighted individual objectives</label>
    <ScoringNote weighted={weighted} /><CriteriaEditor value={criteria} onChange={setCriteria} weighted={weighted} />
    <div className="actions"><button className="btn" disabled={busy}>Save template</button><button className="btn ghost" type="button" disabled={busy} onClick={cancel}>Cancel</button></div>
  </form>;
}

export function ScoringNote({ weighted }: { weighted: boolean }) {
  return <p className="ap-note">Manager ratings use a fixed 1–5 scale. {weighted ? "Objective weights must total 100%." : "Objectives have equal weight."} Working behaviours have equal weight. When both sections are present, work results contribute 70% and behaviours 30%; a single section contributes 100%. Employee comments do not change the score.</p>;
}

export function ReviewEditor({ value, records, people, templates, save, cancel, busy }: { value?: Review; records: SimpleAppraisal[]; people: AppraisalPerson[]; templates: AppraisalTemplate[]; save: (data: unknown) => Promise<void>; cancel: () => void; busy: boolean }) {
  const [name, setName] = useState(value?.name || "");
  const [start, setStart] = useState(value?.start_date || ""); const [end, setEnd] = useState(value?.end_date || "");
  const [employeeDue, setEmployeeDue] = useState(value?.employee_deadline || ""); const [managerDue, setManagerDue] = useState(value?.manager_deadline || ""); const [ackDue, setAckDue] = useState(value?.acknowledgement_deadline || "");
  const [template, setTemplate] = useState(value?.template_id || templates[0]?.id || ""); const [preparation, setPreparation] = useState(value?.preparation || "HR");
  const [selected, setSelected] = useState(records.filter(r => r.review_id === value?.id).map(r => r.employee_id));
  const [query, setQuery] = useState(""); const [branch, setBranch] = useState(""); const [department, setDepartment] = useState("");
  const visible = people.filter(p => p.name.toLowerCase().includes(query.toLowerCase()) && (!branch || p.branch_id === branch) && (!department || p.department_id === department));
  const submit = (e: FormEvent) => { e.preventDefault(); void save({ name, start_date: start, end_date: end, employee_deadline: employeeDue, manager_deadline: managerDue, acknowledgement_deadline: ackDue, template_id: template, preparation, employee_ids: selected, version: value?.version }); };
  return <form className="card card-pad ap-form" onSubmit={submit}><h2>{value ? "Edit draft review" : "Create appraisal review"}</h2><p>Choose the work period, deadlines, a shared form and participants. Customize each employee's objectives after saving this draft.</p><div className="form-grid">
    <label className="span-2">Review name<input required maxLength={160} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. July–December 2026 appraisal" /></label>
    <label>Performance period starts<input required type="date" value={start} onChange={e => setStart(e.target.value)} /></label><label>Performance period ends<input required type="date" min={start} value={end} onChange={e => setEnd(e.target.value)} /></label>
    <label>Employee self-review deadline<input required type="date" min={end} value={employeeDue} onChange={e => setEmployeeDue(e.target.value)} /></label><label>Manager assessment and discussion deadline<input required type="date" min={employeeDue} value={managerDue} onChange={e => setManagerDue(e.target.value)} /></label><label>Employee acknowledgement deadline<input required type="date" min={managerDue} value={ackDue} onChange={e => setAckDue(e.target.value)} /></label>
    <label>Appraisal template<select required value={template} disabled={Boolean(value)} onChange={e => setTemplate(e.target.value)}>{templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
    <label className="span-2">Who prepares individual objectives?<select value={preparation} onChange={e => setPreparation(e.target.value as "HR" | "MANAGER")}><option value="HR">HR prepares and confirms each form</option><option value="MANAGER">Assigned managers prepare forms; HR checks and publishes</option></select></label>
  </div><fieldset className="ap-participants"><legend>Participants · {selected.length} selected</legend><div className="ap-filters"><label>Find an employee<input type="search" value={query} onChange={e => setQuery(e.target.value)} /></label><label>Branch<select value={branch} onChange={e => setBranch(e.target.value)}><option value="">All branches</option>{Array.from(new Map(people.map(p => [p.branch_id, p.branch_name || p.branch_id])).entries()).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label><label>Department<select value={department} onChange={e => setDepartment(e.target.value)}><option value="">All departments</option>{Array.from(new Map(people.filter(p => p.department_id).map(p => [p.department_id!, p.department_name || p.department_id!])).entries()).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>
    <div className="actions"><button className="btn ghost small" type="button" onClick={() => setSelected(Array.from(new Set([...selected, ...visible.map(p => p.id)])))}>Select displayed employees</button><button className="btn ghost small" type="button" onClick={() => setSelected(selected.filter(id => !visible.some(p => p.id === id)))}>Deselect displayed</button></div>
    <div className="ap-person-list">{visible.map(p => <label className="ap-check" key={p.id}><input type="checkbox" checked={selected.includes(p.id)} onChange={e => setSelected(e.target.checked ? [...selected, p.id] : selected.filter(id => id !== p.id))} /><span><strong>{p.name}</strong><small>{p.department_name || "No department"} · Appraiser: {people.find(manager => manager.id === p.manager_id)?.name || "Needs assignment"}</small></span></label>)}{!visible.length && <p>No matching employees.</p>}</div>
  </fieldset><div className="actions"><button className="btn" disabled={busy || !selected.length || !template}>Save draft and prepare forms</button><button className="btn ghost" type="button" disabled={busy} onClick={cancel}>Cancel</button></div></form>;
}

export function PreparationEditor({ record, people, peers, save, busy }: { record: SimpleAppraisal; people: AppraisalPerson[]; peers: SimpleAppraisal[]; save: (data: unknown) => Promise<void>; busy: boolean }) {
  const [criteria, setCriteria] = useState(record.criteria); const [manager, setManager] = useState(record.manager_id || ""); const [copyFrom, setCopyFrom] = useState("");
  return <form className="card card-pad ap-form" onSubmit={e => { e.preventDefault(); void save({ version: record.version, manager_id: manager || null, criteria, ready: (e.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "ready" }); }}>
    <h2>Prepare {record.context.employee_name}'s appraisal</h2><p>Changes here affect this employee only. Confirm the objectives and appraiser before marking the form ready.</p>
    {record.permissions.hr ? <label>Assigned appraiser<select value={manager} onChange={e => setManager(e.target.value)}><option value="">Select an appraiser</option>{people.filter(p => p.id !== record.employee_id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label> : <p><strong>Appraiser:</strong> {record.context.manager_name}. Contact HR to change this assignment.</p>}
    {peers.some(p => p.id !== record.id) && <div className="ap-copy"><label>Copy individual objectives from another participant<select value={copyFrom} onChange={e => setCopyFrom(e.target.value)}><option value="">Choose an employee</option>{peers.filter(p => p.id !== record.id).map(p => <option key={p.id} value={p.id}>{p.context.employee_name}</option>)}</select></label><button className="btn ghost small" type="button" disabled={!copyFrom} onClick={() => { const source = peers.find(p => p.id === copyFrom); if (source) setCriteria([...criteria.filter(c => c.section !== "OBJECTIVE"), ...source.criteria.filter(c => c.section === "OBJECTIVE").map(c => ({ ...c, id: crypto.randomUUID() }))]); }}>Replace this employee's objectives with a copy</button></div>}
    <ScoringNote weighted={record.review.template_snapshot.weighted} /><CriteriaEditor value={criteria} onChange={setCriteria} weighted={record.review.template_snapshot.weighted} />
    <div className="actions"><button className="btn ghost" disabled={busy} value="draft">Save preparation draft</button><button className="btn" disabled={busy} value="ready">Save and mark form ready</button></div>
  </form>;
}
