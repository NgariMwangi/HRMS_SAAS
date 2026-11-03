import { FormEvent, ReactNode, useState } from "react";
import { api } from "../api";
import { formatLeaveDays, leaveDayBasisLabel, type LeaveType } from "../types";
import { IconPencil, IconPlus, IconTrash } from "./icons";
import { EmptyState, IconButton } from "../ui";

type Draft = {
  name: string;
  days: string;
  accrued: boolean;
  accrual_per_month: string;
  day_basis: "CALENDAR" | "WORKING";
};

const emptyDraft = (): Draft => ({
  name: "",
  days: "0",
  accrued: false,
  accrual_per_month: "1.75",
  day_basis: "WORKING",
});

function fromRow(row: LeaveType): Draft {
  const accrued = Boolean(row.accrued);
  const yearly = Number(row.days || 0);
  const monthly = Number(row.accrual_per_month || 0);
  return {
    name: row.name,
    days: String(row.days),
    accrued,
    accrual_per_month: accrued ? String(monthly || (yearly ? yearly / 12 : 1.75)) : "1.75",
    day_basis: row.day_basis === "CALENDAR" ? "CALENDAR" : "WORKING",
  };
}

function typePayload(draft: Draft) {
  if (draft.accrued) {
    return {
      accrued: true,
      accrual_per_month: Number(draft.accrual_per_month || 0),
      days: Number(draft.accrual_per_month || 0) * 12,
    };
  }
  return { accrued: false, accrual_per_month: 0, days: Number(draft.days || 0) };
}

export function LeaveTypes({
  token,
  apiBase,
  companyId,
  rows,
  canManage,
  title = "Leave types",
  note = "For accrued types, set how many days are earned each month. Other types use a yearly day pot.",
  lead,
  onChange,
}: {
  token: string;
  apiBase: string;
  companyId: string;
  rows: LeaveType[];
  canManage: boolean;
  title?: string;
  note?: string;
  lead?: ReactNode;
  onChange: (rows: LeaveType[]) => void;
}) {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [edit, setEdit] = useState<Draft>(emptyDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openCreate() {
    setShowForm(true);
    setEditingId(null);
    setDraft(emptyDraft());
    setError(null);
  }

  function closeCreate() {
    setShowForm(false);
    setDraft(emptyDraft());
    setError(null);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !draft.name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<LeaveType>(`${apiBase}/leave-types`, {
        method: "POST",
        token,
        body: JSON.stringify({
          company_id: companyId,
          name: draft.name.trim(),
          ...typePayload(draft),
          day_basis: draft.day_basis,
        }),
      });
      onChange([...rows, saved].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)));
      closeCreate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add leave type");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !editingId || !edit.name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<LeaveType>(`${apiBase}/leave-types/${editingId}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({
          name: edit.name.trim(),
          ...typePayload(edit),
          day_basis: edit.day_basis,
        }),
      });
      onChange(rows.map((row) => (row.id === saved.id ? saved : row)));
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update leave type");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: LeaveType) {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      await api(`${apiBase}/leave-types/${row.id}`, { method: "DELETE", token });
      onChange(rows.filter((item) => item.id !== row.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete leave type");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="card-head">
        <div>
          <h3>{title}</h3>
          <p>{note}</p>
        </div>
        {canManage && !showForm ? (
          <button className="btn small" type="button" onClick={openCreate} style={{ flexShrink: 0 }}>
            <IconPlus /> Add leave type
          </button>
        ) : null}
      </div>
      {lead}
      {canManage && showForm ? (
        <form className="nested-block" onSubmit={create} style={{ margin: "1rem 1.1rem 0" }}>
          <div className="form-grid">
            <label>Name<input required placeholder="e.g. Annual leave" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
            <label>Accrual
              <select value={draft.accrued ? "yes" : "no"} onChange={(event) => setDraft({ ...draft, accrued: event.target.value === "yes" })}>
                <option value="yes">Accrued monthly</option>
                <option value="no">Yearly pot</option>
              </select>
            </label>
            {draft.accrued ? (
              <label>Days earned each month<input required type="number" min={0.01} step="0.01" value={draft.accrual_per_month} onChange={(event) => setDraft({ ...draft, accrual_per_month: event.target.value })} /></label>
            ) : (
              <label>Days<input required type="number" min={0} step="0.5" value={draft.days} onChange={(event) => setDraft({ ...draft, days: event.target.value })} /></label>
            )}
            <label>Counted as
              <select value={draft.day_basis} onChange={(event) => setDraft({ ...draft, day_basis: event.target.value as Draft["day_basis"] })}>
                <option value="WORKING">Working days</option>
                <option value="CALENDAR">Calendar days</option>
              </select>
            </label>
          </div>
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button className="btn ghost small" type="button" onClick={closeCreate}>Cancel</button>
          </div>
        </form>
      ) : null}
      {error ? <p className="error" style={{ margin: "0.75rem 1.1rem 0" }}>{error}</p> : null}
      {rows.length === 0 ? (
        <EmptyState title="No leave types" note="Add Annual, Sick, or another type this company uses." />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Days</th>
              <th>Accrual</th>
              <th>Counted as</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                {editingId === row.id ? (
                  <td colSpan={5}>
                    <form className="form-grid" onSubmit={saveEdit}>
                      <label>Name<input required value={edit.name} onChange={(event) => setEdit({ ...edit, name: event.target.value })} /></label>
                      <label>Accrual
                        <select value={edit.accrued ? "yes" : "no"} onChange={(event) => setEdit({ ...edit, accrued: event.target.value === "yes" })}>
                          <option value="yes">Accrued monthly</option>
                          <option value="no">Yearly pot</option>
                        </select>
                      </label>
                      {edit.accrued ? (
                        <label>Days earned each month<input required type="number" min={0.01} step="0.01" value={edit.accrual_per_month} onChange={(event) => setEdit({ ...edit, accrual_per_month: event.target.value })} /></label>
                      ) : (
                        <label>Days<input required type="number" min={0} step="0.5" value={edit.days} onChange={(event) => setEdit({ ...edit, days: event.target.value })} /></label>
                      )}
                      <label>Counted as
                        <select value={edit.day_basis} onChange={(event) => setEdit({ ...edit, day_basis: event.target.value as Draft["day_basis"] })}>
                          <option value="WORKING">Working days</option>
                          <option value="CALENDAR">Calendar days</option>
                        </select>
                      </label>
                      <div className="actions" style={{ gridColumn: "1 / -1" }}>
                        <button className="btn small" type="submit" disabled={busy}>Save</button>
                        <button className="btn ghost small" type="button" onClick={() => setEditingId(null)}>Cancel</button>
                      </div>
                    </form>
                  </td>
                ) : (
                  <>
                    <td data-label="Type">{row.name}</td>
                    <td data-label="Days">{row.accrued ? `${formatLeaveDays(row.accrual_per_month || Number(row.days) / 12)} / month` : formatLeaveDays(row.days)}</td>
                    <td data-label="Accrual">{row.accrued ? "Accrued monthly" : "Yearly pot"}</td>
                    <td data-label="Counted as">{leaveDayBasisLabel(row.day_basis)}</td>
                    <td className="row-actions">
                      {canManage ? (
                        <>
                          <IconButton
                            label="Edit"
                            onClick={() => { setEditingId(row.id); setEdit(fromRow(row)); setError(null); }}
                          >
                            <IconPencil />
                          </IconButton>
                          <IconButton label="Delete" disabled={busy} onClick={() => void remove(row)}>
                            <IconTrash />
                          </IconButton>
                        </>
                      ) : null}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
