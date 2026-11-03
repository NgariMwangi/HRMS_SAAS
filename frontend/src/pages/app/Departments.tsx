import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { IconPlus } from "../../components/icons";
import type { Department, JobTitle } from "../../types";
import { EmptyState, matchesSearch, PageHeader, SearchField, StatusPill, TableSkeleton } from "../../ui";

type DepartmentForm = {
  name: string;
  code: string;
  description: string;
  status: string;
};

const emptyForm: DepartmentForm = { name: "", code: "", description: "", status: "ACTIVE" };

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

export default function DepartmentsPage() {
  const { token, company, companies, canManageOrg, setCompanyId, notify } = useWorkspace();
  const [rows, setRows] = useState<Department[]>([]);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [editing, setEditing] = useState<Department | null>(null);
  const [form, setForm] = useState<DepartmentForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const phoneList = usePhoneList();

  async function load() {
    if (!company) {
      setRows([]);
      setTitles([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [deptRows, titleRows] = await Promise.all([
        api<Department[]>(`/departments?company_id=${company.id}`, { token }),
        api<JobTitle[]>(`/job-titles?company_id=${company.id}`, { token }),
      ]);
      setRows(deptRows);
      setTitles(titleRows);
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

  const visible = useMemo(
    () => rows.filter((row) => matchesSearch(query, row.name, row.code, row.description)),
    [rows, query],
  );

  const titleCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of titles) {
      if (row.department_id) counts.set(row.department_id, (counts.get(row.department_id) ?? 0) + 1);
    }
    return counts;
  }, [titles]);

  useEffect(() => {
    if (mode === "idle") return;
    document.getElementById("department-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [mode, editing?.id]);

  function startCreate() {
    setMode("create");
    setEditing(null);
    setForm(emptyForm);
    setError(null);
  }

  function startEdit(row: Department) {
    setMode("edit");
    setEditing(row);
    setForm({
      name: row.name,
      code: row.code ?? "",
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
        description: blankToNull(form.description),
        status: form.status,
      };
      if (mode === "create") {
        await api<Department>("/departments", {
          method: "POST",
          token,
          body: JSON.stringify({ ...payload, company_id: company.id }),
        });
        notify(`${payload.name} added to ${company.name}.`);
      } else if (editing) {
        await api<Department>(`/departments/${editing.id}`, {
          method: "PATCH",
          token,
          body: JSON.stringify(payload),
        });
        notify("Department updated.");
      }
      setMode("idle");
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save department");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(row: Department) {
    if (!canManageOrg) return;
    setBusy(true);
    try {
      await api<Department>(`/departments/${row.id}`, {
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

  const departmentForm = (
    <form onSubmit={onSubmit} id="department-form">
      <h3 style={{ fontSize: "1rem", margin: 0 }}>{mode === "create" ? "New department" : "Edit department"}</h3>
      <div className="form-grid">
        <label>Name <span className="req">*</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Code<input value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></label>
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
        title="Departments"
        description="How people are grouped in the selected company. Job titles can sit on a department or on the company."
        actions={
          canManageOrg && company ? (
            mode === "idle" ? (
              <button className="btn small" type="button" onClick={startCreate}><IconPlus /> Add department</button>
            ) : (
              <button className="btn ghost small" type="button" onClick={() => { setMode("idle"); setEditing(null); }}>Close form</button>
            )
          ) : null
        }
      />
      {mode === "create" ? (
        <section className="card card-pad org-form">{departmentForm}</section>
      ) : null}
      <div className="filters" style={{ marginBottom: 14 }}>
        <SearchField value={query} onChange={setQuery} placeholder="Name or code" />
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
        <section className="card"><TableSkeleton cols={5} /></section>
      ) : (
      <div className="titles-stack">
        <section className="card">
          {visible.length === 0 ? (
            <EmptyState
              title={query.trim() ? "No matching departments" : "No departments yet"}
              note={query.trim() ? `Nothing matched “${query.trim()}”.` : "Add People, Finance, or Operations for this company before you add employees."}
              action={!query.trim() && canManageOrg && company && mode === "idle" ? <button className="btn small" type="button" onClick={startCreate}>Add department</button> : null}
            />
          ) : (
            <>
            <table className="titles-table">
              <thead>
                <tr>
                  <th>Department</th>
                  <th>Code</th>
                  <th>Titles</th>
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
                        {row.description ? <div className="muted">{row.description}</div> : null}
                      </td>
                      <td>{row.code ?? "—"}</td>
                      <td>{titleCounts.get(row.id) ?? 0}</td>
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
                        <td colSpan={5}>{departmentForm}</td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <ul className="titles-list">
              {visible.map((row) => {
                const count = titleCounts.get(row.id) ?? 0;
                const meta = [row.code, `${count} ${count === 1 ? "title" : "titles"}`].filter(Boolean).join(" · ");
                return (
                  <Fragment key={row.id}>
                    <li className={editing?.id === row.id ? "titles-row is-active" : "titles-row"}>
                      <div className="titles-row-top">
                        <div className="titles-main">
                          <strong>{row.name}</strong>
                          <span>{meta}</span>
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
                      <li className="titles-inline-form">{departmentForm}</li>
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
