import { FormEvent, useState } from "react";
import type { Person } from "./performanceTypes";
import type { Values } from "./PerformanceForm";

type Group = { id: string; name: string };

export default function PerformanceParticipants({ people, branches, departments, jobTitles, submit, close }: {
  people: Person[]; branches: Group[]; departments: Group[]; jobTitles: Group[];
  submit: (values: Values) => Promise<void>; close: () => void;
}) {
  const [mode, setMode] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [manager, setManager] = useState("");
  const [filters, setFilters] = useState({ branch_id: "", department_id: "", job_title_id: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const filtered = people.filter(person => (!filters.branch_id || person.branch_id === filters.branch_id)
    && (!filters.department_id || person.department_id === filters.department_id)
    && (!filters.job_title_id || person.job_title_id === filters.job_title_id));
  const visible = filtered.filter(person => person.name.toLowerCase().includes(search.toLowerCase()));
  const ids = mode === "all" ? filtered.map(person => person.id) : selected;
  const filteredCount = Object.values(filters).filter(Boolean).length;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ids.length) { setError("Select at least one employee."); return; }
    setBusy(true); setError("");
    try {
      await submit({ employee_ids: mode === "all" ? [] : selected, all_employees: mode === "all", manager_id: manager || null, reviewer_id: null,
        branch_id: mode === "all" ? filters.branch_id || null : null,
        department_id: mode === "all" ? filters.department_id || null : null,
        job_title_id: mode === "all" ? filters.job_title_id || null : null });
      close();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  return <section className="card performance-form" aria-label="Assign review participants">
    <div className="card-head"><div><h3>Assign review participants</h3><p>Choose the employees who will take part in this review.</p></div><button className="btn ghost small" type="button" disabled={busy} onClick={close}>Close</button></div>
    <form className="card-pad" onSubmit={save}>
      {error && <p className="error" role="alert">{error}</p>}
      <fieldset className="performance-fields" disabled={busy}>
        <div className="participant-choices">
          <label><input type="radio" name="participants" checked={mode === "all"} onChange={() => setMode("all")} /><span><strong>{filteredCount ? "All filtered employees" : "All employees"}</strong><small>{filtered.length} employees</small></span></label>
          <label><input type="radio" name="participants" checked={mode === "selected"} onChange={() => setMode("selected")} /><span><strong>Select employees</strong><small>Choose specific people</small></span></label>
        </div>
        {mode === "selected" && <div className="participant-picker"><label>Find an employee<input type="search" value={search} placeholder="Search by name" onChange={event => setSearch(event.target.value)} /></label><div className="participant-list">{visible.length ? visible.map(person => <label key={person.id}><input type="checkbox" checked={selected.includes(person.id)} onChange={event => setSelected(current => event.target.checked ? [...current, person.id] : current.filter(id => id !== person.id))} /><span>{person.name}</span></label>) : <p>No employees match.</p>}</div><small>{selected.length} selected</small></div>}
        <label className="participant-manager">Manager / supervisor<select value={manager} onChange={event => setManager(event.target.value)}><option value="">Use each employee's existing supervisor</option>{people.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select><small>Optional: choose someone only if you want to replace the usual supervisor for this review.</small></label>
        <details className="participant-filters"><summary>Filter employees{filteredCount ? ` (${filteredCount} active)` : ""}</summary><div className="form-grid">{([
          ["branch_id", "Branch", branches], ["department_id", "Department", departments], ["job_title_id", "Job title", jobTitles],
        ] as const).map(([key, label, groups]) => <label key={key}>{label}<select value={filters[key]} onChange={event => setFilters(current => ({ ...current, [key]: event.target.value }))}><option value="">All {label.toLowerCase()}s</option>{groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>)}</div>{filteredCount > 0 && <button className="btn ghost small" type="button" onClick={() => setFilters({ branch_id: "", department_id: "", job_title_id: "" })}>Clear filters</button>}</details>
        <div className="actions"><button className="btn" type="submit" disabled={!ids.length}>{busy ? "Assigning…" : `Assign ${ids.length} employee${ids.length === 1 ? "" : "s"}`}</button><button className="btn ghost" type="button" onClick={close}>Cancel</button></div>
      </fieldset>
    </form>
  </section>;
}
