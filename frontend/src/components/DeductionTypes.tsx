import { FormEvent, useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import { deductionCategoryLabel, type DeductionCategory, type DeductionType } from "../types";
import { EmptyState, FormSkeleton, StatusPill, formatMoney, matchesSearch } from "../ui";

type EnrolCandidate = {
  employee_id: string;
  name: string;
  employee_number: string;
  branch_id: string;
  enrolled: boolean;
};

type Draft = {
  name: string;
  category: DeductionCategory;
  default_amount: string;
  is_active: boolean;
};

const emptyDraft = (): Draft => ({ name: "", category: "PERSONAL", default_amount: "", is_active: true });

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function DeductionTypes({
  token,
  apiBase = "",
  company,
  branch,
  currency,
  canManage,
  notify,
}: {
  token: string;
  apiBase?: string;
  company: { id: string; name: string } | null;
  branch: { id: string; name: string } | null;
  currency?: string | null;
  canManage: boolean;
  notify: (message: string) => void;
}) {
  const [rows, setRows] = useState<DeductionType[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"closed" | "add" | "edit">("closed");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [enrolling, setEnrolling] = useState<DeductionType | null>(null);
  const [enrolAmount, setEnrolAmount] = useState("");
  const [enrolStart, setEnrolStart] = useState(today);
  const [enrolScope, setEnrolScope] = useState<"branch" | "company">("branch");
  const [candidates, setCandidates] = useState<EnrolCandidate[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickSearch, setPickSearch] = useState("");
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<DeductionType[]>(apiUrl(apiBase, `/deduction-types?company_id=${company.id}`), { token })
      .then((list) => {
        setRows(list);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [company?.id, token, apiBase]);

  useEffect(() => {
    if (!enrolling) {
      setCandidates([]);
      return;
    }
    const scopeBranch = enrolScope === "branch" && branch ? `?branch_id=${branch.id}` : "";
    setLoadingCandidates(true);
    api<EnrolCandidate[]>(apiUrl(apiBase, `/deduction-types/${enrolling.id}/enrol${scopeBranch}`), { token })
      .then((list) => {
        setCandidates(list);
        setPicked(new Set(list.filter((row) => !row.enrolled).map((row) => row.employee_id)));
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingCandidates(false));
  }, [enrolling?.id, enrolScope, branch?.id, token, apiBase]);

  const visibleCandidates = candidates.filter((row) => matchesSearch(pickSearch, row.name, row.employee_number));
  const pickable = visibleCandidates.filter((row) => !row.enrolled);

  function togglePick(employeeId: string) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  }

  function pickVisible(on: boolean) {
    setPicked((current) => {
      const next = new Set(current);
      for (const row of pickable) {
        if (on) next.add(row.employee_id);
        else next.delete(row.employee_id);
      }
      return next;
    });
  }

  function openAdd() {
    setMode("add");
    setEditingId(null);
    setDraft(emptyDraft());
    setEnrolling(null);
    setError(null);
  }

  function openEdit(row: DeductionType) {
    setMode("edit");
    setEditingId(row.id);
    setDraft({
      name: row.name,
      category: row.category,
      default_amount: row.default_amount ?? "",
      is_active: row.is_active,
    });
    setEnrolling(null);
    setError(null);
  }

  function openEnrol(row: DeductionType) {
    setMode("closed");
    setEnrolling(row);
    setEnrolAmount(row.default_amount ?? "");
    setEnrolStart(today());
    setEnrolScope(branch ? "branch" : "company");
    setPickSearch("");
    setError(null);
  }

  function sortRows(list: DeductionType[]) {
    return [...list].sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!company || !canManage) return;
    setBusy(true);
    setError(null);
    const body = {
      name: draft.name.trim(),
      category: draft.category,
      default_amount: draft.default_amount || null,
      is_active: draft.is_active,
    };
    try {
      if (mode === "edit" && editingId) {
        const saved = await api<DeductionType>(apiUrl(apiBase, `/deduction-types/${editingId}`), {
          method: "PATCH",
          token,
          body: JSON.stringify(body),
        });
        setRows((current) => sortRows(current.map((row) => (row.id === saved.id ? saved : row))));
        notify("Deduction type updated.");
      } else {
        const saved = await api<DeductionType>(apiUrl(apiBase, "/deduction-types"), {
          method: "POST",
          token,
          body: JSON.stringify({ ...body, company_id: company.id }),
        });
        setRows((current) => sortRows([...current, saved]));
        notify("Deduction type added.");
      }
      setMode("closed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save deduction type");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: DeductionType) {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/deduction-types/${row.id}`), { method: "DELETE", token });
      setRows((current) => current.filter((item) => item.id !== row.id));
      notify("Deduction type deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete deduction type");
    } finally {
      setBusy(false);
    }
  }

  async function enrol(event: FormEvent) {
    event.preventDefault();
    if (!enrolling || !canManage) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ enrolled: number; already_enrolled: number }>(
        apiUrl(apiBase, `/deduction-types/${enrolling.id}/enrol`),
        {
          method: "POST",
          token,
          body: JSON.stringify({
            amount: enrolAmount || null,
            start_date: enrolStart,
            branch_id: enrolScope === "branch" && branch ? branch.id : null,
            employee_ids: [...picked],
          }),
        },
      );
      notify(
        `${result.enrolled} employee${result.enrolled === 1 ? "" : "s"} enrolled in ${enrolling.name}` +
          (result.already_enrolled ? ` (${result.already_enrolled} already enrolled).` : "."),
      );
      setEnrolling(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not enrol employees");
    } finally {
      setBusy(false);
    }
  }

  if (!company) return null;

  return (
    <section className="card" style={{ marginTop: "1rem" }}>
      <div className="card-head">
        <div>
          <h3>Other deductions</h3>
          <p>
            Loans, HELB, SACCO and company schemes such as Welfare. They come off net pay after PAYE. Assign them to
            people on each employee's Salary page, or enrol everyone in a company scheme here.
          </p>
        </div>
        {canManage && mode === "closed" ? (
          <button className="btn small" type="button" onClick={openAdd} style={{ flexShrink: 0 }}>
            Add deduction type
          </button>
        ) : null}
      </div>

      {canManage && mode !== "closed" ? (
        <form className="nested-block" onSubmit={save} style={{ margin: "1rem 1.1rem 0" }}>
          <div className="form-grid">
            <label>
              Name
              <input
                required
                maxLength={100}
                placeholder="e.g. Staff loan, Sacco, Welfare Kit"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </label>
            <label>
              Category
              <select
                value={draft.category}
                onChange={(event) => setDraft({ ...draft, category: event.target.value as DeductionCategory })}
              >
                <option value="PERSONAL">Personal (loan, HELB, SACCO…)</option>
                <option value="COMPANY">Company scheme (welfare…)</option>
              </select>
            </label>
            <label>
              Default amount per period
              <input
                type="number"
                min="0.01"
                step="0.01"
                placeholder="Optional"
                value={draft.default_amount}
                onChange={(event) => setDraft({ ...draft, default_amount: event.target.value })}
              />
            </label>
            {mode === "edit" ? (
              <label>
                Status
                <select
                  value={draft.is_active ? "active" : "inactive"}
                  onChange={(event) => setDraft({ ...draft, is_active: event.target.value === "active" })}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive (no new assignments)</option>
                </select>
              </label>
            ) : null}
          </div>
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button className="btn ghost small" type="button" onClick={() => setMode("closed")}>Cancel</button>
          </div>
        </form>
      ) : null}

      {canManage && enrolling ? (
        <form className="nested-block" onSubmit={enrol} style={{ margin: "1rem 1.1rem 0" }}>
          <p style={{ marginTop: 0 }}>
            Enrol employees in <strong>{enrolling.name}</strong> as a recurring deduction. Untick anyone who should be
            left out. You can stop or change it per person later on their Salary page.
          </p>
          <div className="form-grid">
            <label>
              Amount per period
              <input
                required={!enrolling.default_amount}
                type="number"
                min="0.01"
                step="0.01"
                value={enrolAmount}
                onChange={(event) => setEnrolAmount(event.target.value)}
              />
            </label>
            <label>
              Starting from
              <input type="date" required value={enrolStart} onChange={(event) => setEnrolStart(event.target.value)} />
            </label>
            <label>
              Who
              <select value={enrolScope} onChange={(event) => setEnrolScope(event.target.value as "branch" | "company")}>
                {branch ? <option value="branch">Employees in {branch.name}</option> : null}
                <option value="company">All employees in {company.name}</option>
              </select>
            </label>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
              <input
                type="search"
                placeholder="Search by name or number"
                value={pickSearch}
                onChange={(event) => setPickSearch(event.target.value)}
                style={{ flex: "1 1 14rem" }}
              />
              <button className="btn ghost small" type="button" onClick={() => pickVisible(true)}>Select all</button>
              <button className="btn ghost small" type="button" onClick={() => pickVisible(false)}>Clear</button>
              <span className="muted">{picked.size} selected</span>
            </div>
            <div
              style={{
                maxHeight: "16rem",
                overflowY: "auto",
                marginTop: 8,
                border: "1px solid var(--border, #e2e8f0)",
                borderRadius: 8,
              }}
            >
              {loadingCandidates ? (
                <p className="muted card-pad" style={{ margin: 0 }}>Loading employees…</p>
              ) : visibleCandidates.length === 0 ? (
                <p className="muted card-pad" style={{ margin: 0 }}>No active employees match.</p>
              ) : (
                visibleCandidates.map((row) => (
                  <label
                    key={row.employee_id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.6rem",
                      padding: "0.45rem 0.75rem",
                      cursor: row.enrolled ? "default" : "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      style={{ width: "auto" }}
                      disabled={row.enrolled}
                      checked={row.enrolled || picked.has(row.employee_id)}
                      onChange={() => togglePick(row.employee_id)}
                    />
                    <span>
                      {row.name} <span className="muted">· {row.employee_number}</span>
                      {row.enrolled ? <span className="muted"> · already enrolled</span> : null}
                    </span>
                  </label>
                ))
              )}
            </div>
          </div>
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn small" type="submit" disabled={busy || picked.size === 0}>
              {busy ? "Enrolling…" : `Enrol ${picked.size} employee${picked.size === 1 ? "" : "s"}`}
            </button>
            <button className="btn ghost small" type="button" onClick={() => setEnrolling(null)}>Cancel</button>
          </div>
        </form>
      ) : null}

      {error ? <p className="error" style={{ margin: "0.75rem 1.1rem 0" }}>{error}</p> : null}

      {loading ? (
        <div className="card-pad"><FormSkeleton compact fields={2} /></div>
      ) : rows.length === 0 ? (
        <EmptyState title="No deduction types yet" note="Add the loans, SACCOs and schemes your payroll deducts." />
      ) : (
        <table className="org-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Category</th>
              <th>Default amount</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Name">{row.name}</td>
                <td data-label="Category">{deductionCategoryLabel[row.category]}</td>
                <td data-label="Default amount">
                  {row.default_amount ? formatMoney(row.default_amount, currency) : <span className="muted">—</span>}
                </td>
                <td data-label="Status"><StatusPill value={row.is_active ? "ACTIVE" : "INACTIVE"} /></td>
                <td className="row-actions">
                  {canManage ? (
                    <>
                      {row.is_active ? (
                        <button className="btn ghost small" type="button" disabled={busy} onClick={() => openEnrol(row)}>
                          Enrol employees
                        </button>
                      ) : null}
                      <button className="btn ghost small" type="button" disabled={busy} onClick={() => openEdit(row)}>Edit</button>
                      <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(row)}>Delete</button>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
