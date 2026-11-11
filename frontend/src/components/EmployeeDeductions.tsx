import { FormEvent, useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import { deductionCategoryLabel, type DeductionType, type EmployeeDeduction } from "../types";
import { EmptyState, StatusPill, formatDate, formatMoney } from "../ui";

type Draft = {
  deduction_type_id: string;
  title: string;
  category: string;
  frequency: "RECURRING" | "ONE_OFF";
  amount: string;
  start_date: string;
  end_date: string;
  total_amount: string;
  reference: string;
  status: "ACTIVE" | "STOPPED";
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const emptyDraft = (): Draft => ({
  deduction_type_id: "",
  title: "",
  category: "PERSONAL",
  frequency: "RECURRING",
  amount: "",
  start_date: today(),
  end_date: "",
  total_amount: "",
  reference: "",
  status: "ACTIVE",
});

function fromRow(row: EmployeeDeduction): Draft {
  return {
    deduction_type_id: row.deduction_type_id,
    title: row.type_name,
    category: row.category,
    frequency: row.frequency,
    amount: row.amount,
    start_date: row.start_date,
    end_date: row.end_date ?? "",
    total_amount: row.total_amount ?? "",
    reference: row.reference ?? "",
    status: row.status,
  };
}

function payload(draft: Draft) {
  const recurring = draft.frequency === "RECURRING";
  return {
    deduction_type_id: draft.deduction_type_id || undefined,
    title: draft.deduction_type_id ? undefined : draft.title.trim(),
    category: draft.category,
    frequency: draft.frequency,
    amount: draft.amount,
    start_date: draft.start_date,
    end_date: recurring && draft.end_date ? draft.end_date : null,
    total_amount: recurring && draft.total_amount ? draft.total_amount : null,
    reference: draft.reference.trim() || null,
    status: draft.status,
  };
}

export function EmployeeDeductions({
  token,
  apiBase = "",
  employeeId,
  companyId,
  currency,
  canManage,
  notify,
}: {
  token: string;
  apiBase?: string;
  employeeId: string;
  companyId: string;
  currency?: string | null;
  canManage: boolean;
  notify: (message: string) => void;
}) {
  const [rows, setRows] = useState<EmployeeDeduction[]>([]);
  const [types, setTypes] = useState<DeductionType[]>([]);
  const [mode, setMode] = useState<"closed" | "add" | "edit">("closed");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const [list, kinds] = await Promise.all([
      api<EmployeeDeduction[]>(apiUrl(apiBase, `/employees/${employeeId}/deductions`), { token }),
      api<DeductionType[]>(apiUrl(apiBase, `/deduction-types?company_id=${companyId}`), { token }),
    ]);
    setRows(list);
    setTypes(kinds);
  }

  useEffect(() => {
    if (!canManage) return;
    load()
      .then(() => setError(null))
      .catch((err: Error) => setError(err.message));
  }, [employeeId, companyId, token, apiBase, canManage]);

  const activeTypes = types.filter((row) => row.is_active || row.id === draft.deduction_type_id);

  function pickTitle(title: string) {
    const kind = activeTypes.find(row => row.name.toLowerCase() === title.trim().toLowerCase());
    setDraft(current => ({ ...current, title,
      deduction_type_id: kind?.id ?? "",
      amount: current.amount || kind?.default_amount || "",
      category: kind?.category ?? current.category,
    }));
  }

  function openAdd() {
    setMode("add");
    setEditingId(null);
    setDraft(emptyDraft());
    setError(null);
  }

  function openEdit(row: EmployeeDeduction) {
    setMode("edit");
    setEditingId(row.id);
    setDraft(fromRow(row));
    setError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "edit" && editingId) {
        await api(apiUrl(apiBase, `/employees/${employeeId}/deductions/${editingId}`), {
          method: "PATCH",
          token,
          body: JSON.stringify(payload(draft)),
        });
        notify("Deduction updated.");
      } else {
        await api(apiUrl(apiBase, `/employees/${employeeId}/deductions`), {
          method: "POST",
          token,
          body: JSON.stringify(payload(draft)),
        });
        notify("Deduction added.");
      }
      setMode("closed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save deduction");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(row: EmployeeDeduction, status: "ACTIVE" | "STOPPED") {
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/employees/${employeeId}/deductions/${row.id}`), {
        method: "PATCH",
        token,
        body: JSON.stringify({ ...payload(fromRow(row)), status }),
      });
      notify(status === "STOPPED" ? "Deduction stopped." : "Deduction resumed.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update deduction");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: EmployeeDeduction) {
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/employees/${employeeId}/deductions/${row.id}`), { method: "DELETE", token });
      notify("Deduction deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete deduction");
    } finally {
      setBusy(false);
    }
  }

  if (!canManage) return null;

  const recurring = draft.frequency === "RECURRING";

  return (
    <section className="card" style={{ marginTop: "1rem" }}>
      <div className="card-head">
        <div>
          <h3>Other deductions</h3>
          <p>Loans, SACCO, HELB, welfare and other deductions taken from net pay after PAYE.</p>
        </div>
        {mode === "closed" ? (
          <button className="btn small" type="button" onClick={openAdd} style={{ flexShrink: 0 }}>Add deduction</button>
        ) : null}
      </div>

      {mode !== "closed" ? (
        <form className="nested-block" onSubmit={submit} style={{ margin: "1rem 1.1rem 0" }}>
          <div className="form-grid">
            <label>
              Deduction
              <input required maxLength={100} list={`${employeeId}-deduction-titles`} value={draft.title} onChange={event => pickTitle(event.target.value)} placeholder="Choose an existing title or type a new one" />
              <datalist id={`${employeeId}-deduction-titles`}>
                {activeTypes.map(row => <option key={row.id} value={row.name} />)}
              </datalist>
            </label>
            {!draft.deduction_type_id && <label>Category<select value={draft.category} onChange={event => setDraft({ ...draft, category: event.target.value })}><option value="PERSONAL">Personal</option><option value="COMPANY">Company scheme</option></select></label>}
            <label>
              How often
              <select
                value={draft.frequency}
                onChange={(event) => setDraft({ ...draft, frequency: event.target.value as Draft["frequency"] })}
              >
                <option value="RECURRING">Every pay period</option>
                <option value="ONE_OFF">Once</option>
              </select>
            </label>
            <label>
              {recurring ? "Amount per period" : "Amount"}
              <input
                required
                type="number"
                min="0.01"
                step="0.01"
                value={draft.amount}
                onChange={(event) => setDraft({ ...draft, amount: event.target.value })}
              />
            </label>
            <label>
              {recurring ? "Starts from" : "Deduct in the pay period containing"}
              <input
                required
                type="date"
                value={draft.start_date}
                onChange={(event) => setDraft({ ...draft, start_date: event.target.value })}
              />
            </label>
            {recurring ? (
              <>
                <label>
                  Total to recover (loans)
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="Optional – stops when reached"
                    value={draft.total_amount}
                    onChange={(event) => setDraft({ ...draft, total_amount: event.target.value })}
                  />
                </label>
                <label>
                  Ends on
                  <input
                    type="date"
                    value={draft.end_date}
                    onChange={(event) => setDraft({ ...draft, end_date: event.target.value })}
                  />
                </label>
              </>
            ) : null}
            <label>
              Reference
              <input
                maxLength={100}
                placeholder="Loan no., member no. (optional)"
                value={draft.reference}
                onChange={(event) => setDraft({ ...draft, reference: event.target.value })}
              />
            </label>
          </div>
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button className="btn ghost small" type="button" onClick={() => setMode("closed")}>Cancel</button>
          </div>
        </form>
      ) : null}

      {error ? <p className="error" style={{ margin: "0.75rem 1.1rem 0" }}>{error}</p> : null}

      {rows.length === 0 ? (
        <EmptyState title="No other deductions" note="This person has no loans, SACCO or scheme deductions." />
      ) : (
        <table className="org-table">
          <thead>
            <tr>
              <th>Deduction</th>
              <th>Schedule</th>
              <th>Amount</th>
              <th>Recovered</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Deduction">
                  {row.type_name}
                  <span className="muted">
                    {" · "}
                    {deductionCategoryLabel[row.category]}
                    {row.reference ? ` · ${row.reference}` : ""}
                  </span>
                </td>
                <td data-label="Schedule">
                  {row.frequency === "ONE_OFF"
                    ? `Once, period of ${formatDate(row.start_date)}`
                    : `Every period from ${formatDate(row.start_date)}${row.end_date ? ` to ${formatDate(row.end_date)}` : ""}`}
                </td>
                <td data-label="Amount">{formatMoney(row.amount, currency)}</td>
                <td data-label="Recovered">
                  {formatMoney(row.recovered, currency)}
                  {row.total_amount ? <span className="muted"> of {formatMoney(row.total_amount, currency)}</span> : null}
                  {row.balance !== null && row.frequency === "RECURRING" ? (
                    <span className="muted"> · balance {formatMoney(row.balance, currency)}</span>
                  ) : null}
                </td>
                <td data-label="Status">
                  <StatusPill value={row.balance !== null && Number(row.balance) <= 0 ? "COMPLETED" : row.status} />
                </td>
                <td className="row-actions">
                  <button className="btn ghost small" type="button" disabled={busy} onClick={() => openEdit(row)}>Edit</button>
                  {row.status === "ACTIVE" ? (
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => void setStatus(row, "STOPPED")}>Stop</button>
                  ) : (
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => void setStatus(row, "ACTIVE")}>Resume</button>
                  )}
                  {Number(row.recovered) <= 0 ? (
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(row)}>Delete</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted card-pad" style={{ margin: 0 }}>
        Amounts count as recovered once a payroll run is approved. Draft runs show what will be deducted.
      </p>
    </section>
  );
}
