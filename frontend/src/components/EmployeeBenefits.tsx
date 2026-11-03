import { FormEvent, useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import type { BenefitType, EmployeeBenefit } from "../types";
import { EmptyState, StatusPill, formatDate, formatMoney } from "../ui";

type Draft = {
  benefit_type_id: string;
  note: string;
  frequency: "RECURRING" | "ONE_OFF";
  amount: string;
  start_date: string;
  end_date: string;
  status: "ACTIVE" | "STOPPED";
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const emptyDraft = (): Draft => ({
  benefit_type_id: "",
  note: "",
  frequency: "ONE_OFF",
  amount: "",
  start_date: today(),
  end_date: "",
  status: "ACTIVE",
});

function fromRow(row: EmployeeBenefit): Draft {
  return {
    benefit_type_id: row.benefit_type_id,
    note: row.note ?? "",
    frequency: row.frequency,
    amount: row.amount,
    start_date: row.start_date,
    end_date: row.end_date ?? "",
    status: row.status,
  };
}

function payload(draft: Draft) {
  const recurring = draft.frequency === "RECURRING";
  return {
    benefit_type_id: draft.benefit_type_id,
    note: draft.note.trim() || null,
    frequency: draft.frequency,
    amount: draft.amount,
    start_date: draft.start_date,
    end_date: recurring && draft.end_date ? draft.end_date : null,
    status: draft.status,
  };
}

export function EmployeeBenefits({
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
  const [rows, setRows] = useState<EmployeeBenefit[]>([]);
  const [types, setTypes] = useState<BenefitType[]>([]);
  const [mode, setMode] = useState<"closed" | "add" | "edit">("closed");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const [list, kinds] = await Promise.all([
      api<EmployeeBenefit[]>(apiUrl(apiBase, `/employees/${employeeId}/benefits`), { token }),
      api<BenefitType[]>(apiUrl(apiBase, `/benefit-types?company_id=${companyId}`), { token }),
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

  const activeTypes = types.filter((row) => row.is_active || row.id === draft.benefit_type_id);

  function pickType(typeId: string) {
    const kind = types.find((row) => row.id === typeId);
    setDraft((current) => ({
      ...current,
      benefit_type_id: typeId,
      amount: current.amount || kind?.default_amount || "",
    }));
  }

  function openAdd() {
    setMode("add");
    setEditingId(null);
    setDraft(emptyDraft());
    setError(null);
  }

  function openEdit(row: EmployeeBenefit) {
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
        await api(apiUrl(apiBase, `/employees/${employeeId}/benefits/${editingId}`), {
          method: "PATCH",
          token,
          body: JSON.stringify(payload(draft)),
        });
        notify("Benefit updated.");
      } else {
        await api(apiUrl(apiBase, `/employees/${employeeId}/benefits`), {
          method: "POST",
          token,
          body: JSON.stringify(payload(draft)),
        });
        notify("Benefit added.");
      }
      setMode("closed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save benefit");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(row: EmployeeBenefit, status: "ACTIVE" | "STOPPED") {
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/employees/${employeeId}/benefits/${row.id}`), {
        method: "PATCH",
        token,
        body: JSON.stringify({ ...payload(fromRow(row)), status }),
      });
      notify(status === "STOPPED" ? "Benefit stopped." : "Benefit resumed.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update benefit");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: EmployeeBenefit) {
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/employees/${employeeId}/benefits/${row.id}`), { method: "DELETE", token });
      notify("Benefit deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete benefit");
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
          <h3>Benefits</h3>
          <p>Commission, bonuses and other extra earnings. They are added to gross pay, so PAYE and statutory deductions apply.</p>
        </div>
        {mode === "closed" && types.length ? (
          <button className="btn small" type="button" onClick={openAdd} style={{ flexShrink: 0 }}>Add benefit</button>
        ) : null}
      </div>

      {mode !== "closed" ? (
        <form className="nested-block" onSubmit={submit} style={{ margin: "1rem 1.1rem 0" }}>
          <div className="form-grid">
            <label>
              Benefit
              <select required value={draft.benefit_type_id} onChange={(event) => pickType(event.target.value)}>
                <option value="" disabled>Select…</option>
                {activeTypes.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label>
              How often
              <select
                value={draft.frequency}
                onChange={(event) => setDraft({ ...draft, frequency: event.target.value as Draft["frequency"] })}
              >
                <option value="ONE_OFF">Once</option>
                <option value="RECURRING">Every pay period for a date range</option>
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
              {recurring ? "From" : "Pay in the pay period containing"}
              <input
                required
                type="date"
                value={draft.start_date}
                onChange={(event) => setDraft({ ...draft, start_date: event.target.value })}
              />
            </label>
            {recurring ? (
              <label>
                To
                <input
                  type="date"
                  min={draft.start_date}
                  value={draft.end_date}
                  onChange={(event) => setDraft({ ...draft, end_date: event.target.value })}
                />
              </label>
            ) : null}
            <label>
              Note
              <input
                maxLength={100}
                placeholder="e.g. Q1 sales target (optional)"
                value={draft.note}
                onChange={(event) => setDraft({ ...draft, note: event.target.value })}
              />
            </label>
          </div>
          {recurring && !draft.end_date ? (
            <p className="muted" style={{ margin: "8px 0 0" }}>No end date: it is paid every period until you stop it.</p>
          ) : null}
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button className="btn ghost small" type="button" onClick={() => setMode("closed")}>Cancel</button>
          </div>
        </form>
      ) : null}

      {error ? <p className="error" style={{ margin: "0.75rem 1.1rem 0" }}>{error}</p> : null}

      {types.length === 0 ? (
        <EmptyState
          title="No benefit types yet"
          note="Add types such as Commission, Bonus or Overtime under Payroll → Configuration first."
        />
      ) : rows.length === 0 ? (
        <EmptyState title="No benefits" note="This person has no commission, bonus or other benefits." />
      ) : (
        <table className="org-table">
          <thead>
            <tr>
              <th>Benefit</th>
              <th>Schedule</th>
              <th>Amount</th>
              <th>Paid so far</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Benefit">
                  {row.type_name}
                  {row.note ? <span className="muted">{` · ${row.note}`}</span> : null}
                </td>
                <td data-label="Schedule">
                  {row.frequency === "ONE_OFF"
                    ? `Once, period of ${formatDate(row.start_date)}`
                    : `Every period from ${formatDate(row.start_date)}${row.end_date ? ` to ${formatDate(row.end_date)}` : ""}`}
                </td>
                <td data-label="Amount">{formatMoney(row.amount, currency)}</td>
                <td data-label="Paid so far">{formatMoney(row.paid, currency)}</td>
                <td data-label="Status"><StatusPill value={row.status} /></td>
                <td className="row-actions">
                  <button className="btn ghost small" type="button" disabled={busy} onClick={() => openEdit(row)}>Edit</button>
                  {row.status === "ACTIVE" ? (
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => void setStatus(row, "STOPPED")}>Stop</button>
                  ) : (
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => void setStatus(row, "ACTIVE")}>Resume</button>
                  )}
                  {Number(row.paid) <= 0 ? (
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(row)}>Delete</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted card-pad" style={{ margin: 0 }}>
        Amounts count as paid once a payroll run is approved. Draft runs show what will be paid.
      </p>
    </section>
  );
}
