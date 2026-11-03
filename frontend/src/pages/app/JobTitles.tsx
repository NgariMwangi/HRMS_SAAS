import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { IconPlus } from "../../components/icons";
import type { Department, JobTitle } from "../../types";
import { EmptyState, matchesSearch, PageHeader, SearchField, StatusPill, TableSkeleton } from "../../ui";

type TitleForm = {
  name: string;
  code: string;
  department_id: string;
  description: string;
  status: string;
};

const emptyForm: TitleForm = { name: "", code: "", department_id: "", description: "", status: "ACTIVE" };

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function usePhoneList() {
  const [phone, setPhone] = useState(() => window.matchMedia("(max-width: 800px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 800px)");
    const sync = () => setPhone(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return phone;
}

export default function JobTitlesPage() {
  const { token, company, companies, canManageOrg, setCompanyId, notify } = useWorkspace();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [rows, setRows] = useState<JobTitle[]>([]);
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [editing, setEditing] = useState<JobTitle | null>(null);
  const [form, setForm] = useState<TitleForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const phoneList = usePhoneList();

  async function load() {
    if (!company) {
      setDepartments([]);
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [deptRows, titleRows] = await Promise.all([
        api<Department[]>(`/departments?company_id=${company.id}`, { token }),
        api<JobTitle[]>(`/job-titles?company_id=${company.id}`, { token }),
      ]);
      setDepartments(deptRows);
      setRows(titleRows);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setQuery("");
    load().catch((err: Error) => {
      setError(err.message);
      setLoading(false);
    });
  }, [company?.id, token]);

  const departmentById = useMemo(
    () => new Map(departments.map((row) => [row.id, row])),
    [departments],
  );
  const visible = useMemo(
    () => rows.filter((row) => matchesSearch(query, row.name, row.code, row.description, row.department_id ? departmentById.get(row.department_id)?.name : "Company-wide")),
    [rows, query, departmentById],
  );

  useEffect(() => {
    if (mode === "idle") return;
    document.getElementById("job-title-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [mode, editing?.id]);

  function startCreate() {
    setMode("create");
    setEditing(null);
    setForm(emptyForm);
    setError(null);
  }

  function startEdit(row: JobTitle) {
    setMode("edit");
    setEditing(row);
    setForm({
      name: row.name,
      code: row.code ?? "",
      department_id: row.department_id ?? "",
      description: row.description ?? "",
      status: row.status,
    });
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canManageOrg || !company) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        name: form.name.trim(),
        code: blankToNull(form.code),
        department_id: form.department_id || null,
        description: blankToNull(form.description),
        status: form.status,
      };
      if (mode === "create") {
        await api<JobTitle>("/job-titles", {
          method: "POST",
          token,
          body: JSON.stringify({ ...payload, company_id: company.id }),
        });
        notify(`${payload.name} added to ${company.name}.`);
      } else if (editing) {
        await api<JobTitle>(`/job-titles/${editing.id}`, {
          method: "PATCH",
          token,
          body: JSON.stringify(payload),
        });
        notify("Job title updated.");
      }
      setMode("idle");
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save job title");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(row: JobTitle) {
    if (!canManageOrg) return;
    setBusy(true);
    try {
      await api<JobTitle>(`/job-titles/${row.id}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({ status: row.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }),
      });
      await load();
      notify(row.status === "ACTIVE" ? `${row.name} marked inactive.` : `${row.name} reactivated.`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not update status");
    } finally {
      setBusy(false);
    }
  }

  const titleForm = (
    <form onSubmit={onSubmit} id="job-title-form">
      <h3 style={{ fontSize: "1rem", margin: 0 }}>{mode === "create" ? "New job title" : "Edit job title"}</h3>
      <div className="form-grid">
        <label>Name <span className="req">*</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Code<input value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></label>
        <label>Department
          <select value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })}>
            <option value="">Company-wide</option>
            {departments.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
        <label>Status
          <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
        </label>
        <label style={{ gridColumn: "1 / -1" }}>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button className="btn ghost" type="button" onClick={() => { setMode("idle"); setEditing(null); }}>Cancel</button>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </form>
  );

  return (
    <div className="titles-page">
      <PageHeader
        title="Job titles"
        description={`Roles people can hold in ${company?.name ?? "this company"}. Link a title to a department, or leave it company-wide.`}
        actions={
          canManageOrg && company ? (
            mode === "idle" ? (
              <button className="btn small" type="button" onClick={startCreate}><IconPlus /> Add job title</button>
            ) : (
              <button className="btn ghost small" type="button" onClick={() => { setMode("idle"); setEditing(null); }}>Close form</button>
            )
          ) : null
        }
      />
      {mode === "create" ? (
        <section className="card card-pad org-form">{titleForm}</section>
      ) : null}
      <div className="filters" style={{ marginBottom: 14 }}>
        <SearchField value={query} onChange={setQuery} placeholder="Title, code, or department" />
        <label>
          Company
          <select value={company?.id ?? ""} onChange={(event) => setCompanyId(event.target.value)}>
            {companies.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <section className="card"><TableSkeleton cols={4} /></section>
      ) : (
      <div className="titles-stack">
        <section className="card">
          {visible.length === 0 ? (
            <EmptyState
              title={query.trim() ? "No matching job titles" : "No job titles yet"}
              note={query.trim() ? `Nothing matched “${query.trim()}”.` : "Add titles such as Accountant or Branch Manager before you hire into this company."}
              action={!query.trim() && canManageOrg && company && mode === "idle" ? <button className="btn small" type="button" onClick={startCreate}>Add job title</button> : null}
            />
          ) : (
            <>
            <table className="titles-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <Fragment key={row.id}>
                    <tr className={editing?.id === row.id ? "is-active" : ""}>
                      <td>
                        <strong>{row.name}</strong>
                        <div className="muted">{row.code || "No code"}</div>
                      </td>
                      <td>{row.department_id ? departmentById.get(row.department_id)?.name ?? "—" : "Company-wide"}</td>
                      <td><StatusPill value={row.status} /></td>
                      <td>
                        {canManageOrg ? (
                          <div className="row-actions">
                            <button className="btn ghost small" type="button" onClick={() => startEdit(row)}>Edit</button>
                            <button className="btn ghost small" type="button" disabled={busy} onClick={() => toggleStatus(row)}>
                              {row.status === "ACTIVE" ? "Deactivate" : "Activate"}
                            </button>
                          </div>
                        ) : null}
                      </td>
                    </tr>
                    {mode === "edit" && editing?.id === row.id && !phoneList ? (
                      <tr className="titles-inline-form">
                        <td colSpan={4}>{titleForm}</td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <ul className="titles-list">
              {visible.map((row) => {
                const department = row.department_id ? departmentById.get(row.department_id)?.name ?? "—" : "Company-wide";
                return (
                  <Fragment key={row.id}>
                    <li className={editing?.id === row.id ? "titles-row is-active" : "titles-row"}>
                      <div className="titles-row-top">
                        <div className="titles-main">
                          <strong>{row.name}</strong>
                          <span>{[department, row.code].filter(Boolean).join(" · ")}</span>
                        </div>
                        <StatusPill value={row.status} />
                      </div>
                      {canManageOrg ? (
                        <div className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => startEdit(row)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => toggleStatus(row)}>
                            {row.status === "ACTIVE" ? "Deactivate" : "Activate"}
                          </button>
                        </div>
                      ) : null}
                    </li>
                    {mode === "edit" && editing?.id === row.id && phoneList ? (
                      <li className="titles-inline-form">{titleForm}</li>
                    ) : null}
                  </Fragment>
                );
              })}
            </ul>
            </>
          )}
        </section>
      </div>
      )}
    </div>
  );
}
