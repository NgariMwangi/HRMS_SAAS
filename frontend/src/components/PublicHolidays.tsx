import { FormEvent, Fragment, useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import { holidayKindLabel, holidayWhen, MONTHS, type PublicHoliday } from "../types";
import { IconPencil, IconPlus, IconTrash } from "./icons";
import { EmptyState, IconButton } from "../ui";

type Draft = {
  name: string;
  kind: "YEARLY" | "ONCE";
  month: string;
  day: string;
  observed_on: string;
};

const emptyDraft = (): Draft => ({
  name: "",
  kind: "YEARLY",
  month: "12",
  day: "12",
  observed_on: "",
});

function fromRow(row: PublicHoliday): Draft {
  return {
    name: row.name,
    kind: row.kind === "ONCE" ? "ONCE" : "YEARLY",
    month: String(row.month ?? 1),
    day: String(row.day ?? 1),
    observed_on: row.observed_on ?? "",
  };
}

function payload(companyId: string, draft: Draft, branchId?: string, countryId?: string) {
  const scope = {
    company_id: companyId,
    ...(branchId ? { branch_id: branchId } : {}),
    ...(countryId ? { country_id: countryId } : {}),
  };
  if (draft.kind === "ONCE") {
    return { ...scope, name: draft.name.trim(), kind: "ONCE", observed_on: draft.observed_on };
  }
  return {
    ...scope,
    name: draft.name.trim(),
    kind: "YEARLY",
    month: Number(draft.month),
    day: Number(draft.day),
  };
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

function HolidayFields({
  draft,
  onChange,
}: {
  draft: Draft;
  onChange: (next: Draft) => void;
}) {
  return (
    <div className="form-grid">
      <label>Name<input required placeholder="e.g. Jamhuri Day" value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} /></label>
      <label>Type
        <select value={draft.kind} onChange={(event) => onChange({ ...draft, kind: event.target.value as Draft["kind"] })}>
          <option value="YEARLY">Every year</option>
          <option value="ONCE">One-off</option>
        </select>
      </label>
      {draft.kind === "YEARLY" ? (
        <>
          <label>Month
            <select value={draft.month} onChange={(event) => onChange({ ...draft, month: event.target.value })}>
              {MONTHS.map((name, index) => (
                <option key={name} value={index + 1}>{name}</option>
              ))}
            </select>
          </label>
          <label>Day<input required type="number" min={1} max={31} value={draft.day} onChange={(event) => onChange({ ...draft, day: event.target.value })} /></label>
        </>
      ) : (
        <label>Date<input required type="date" value={draft.observed_on} onChange={(event) => onChange({ ...draft, observed_on: event.target.value })} /></label>
      )}
    </div>
  );
}

export function PublicHolidays({
  token,
  apiBase = "",
  companyId,
  branchId,
  countryId,
  rows,
  canManage,
  onChange,
}: {
  token: string;
  apiBase?: string;
  companyId: string;
  branchId?: string;
  countryId?: string;
  rows: PublicHoliday[];
  canManage: boolean;
  onChange: (rows: PublicHoliday[]) => void;
}) {
  const phoneList = usePhoneList();
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openCreate() {
    setMode("create");
    setEditingId(null);
    setDraft(emptyDraft());
    setError(null);
  }

  function closeForm() {
    setMode("idle");
    setEditingId(null);
    setDraft(emptyDraft());
    setError(null);
  }

  function openEdit(row: PublicHoliday) {
    setMode("edit");
    setEditingId(row.id);
    setDraft(fromRow(row));
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !draft.name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        const saved = await api<PublicHoliday>(apiUrl(apiBase, "/public-holidays"), {
          method: "POST",
          token,
          body: JSON.stringify(payload(companyId, draft, branchId, countryId)),
        });
        onChange([...rows, saved]);
      } else if (editingId) {
        const saved = await api<PublicHoliday>(apiUrl(apiBase, `/public-holidays/${editingId}`), {
          method: "PATCH",
          token,
          body: JSON.stringify(payload(companyId, draft)),
        });
        onChange(rows.map((row) => (row.id === saved.id ? saved : row)));
      }
      closeForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save holiday");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: PublicHoliday) {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/public-holidays/${row.id}`), { method: "DELETE", token });
      onChange(rows.filter((item) => item.id !== row.id));
      if (editingId === row.id) closeForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete holiday");
    } finally {
      setBusy(false);
    }
  }

  const form = (
    <form onSubmit={onSubmit} id="public-holiday-form">
      <h3 style={{ fontSize: "1rem", margin: 0 }}>{mode === "create" ? "New public holiday" : "Edit public holiday"}</h3>
      <HolidayFields draft={draft} onChange={setDraft} />
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button className="btn ghost" type="button" onClick={closeForm}>Cancel</button>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </form>
  );

  return (
    <div className="titles-page">
      <div className="card-head">
        <div>
          <h3>Public holidays</h3>
          <p>Kenya branches receive the annual public holidays and this year’s gazetted one-off days, including Easter and Idd. Add any later gazetted day as one-off. Working-day leave skips these for that country.</p>
        </div>
        {canManage ? (
          mode === "idle" ? (
            <button className="btn small" type="button" onClick={openCreate}><IconPlus /> Add holiday</button>
          ) : (
            <button className="btn ghost small" type="button" onClick={closeForm}>Close form</button>
          )
        ) : null}
      </div>
      {mode === "create" ? <div className="card-pad org-form">{form}</div> : null}
      {rows.length === 0 ? (
        mode === "create" ? null : (
          <EmptyState title="No public holidays" note="Kenya branches get the annual dates automatically. Add a one-off day this branch observes." />
        )
      ) : (
        <>
          <table className="titles-table">
            <thead>
              <tr>
                <th>Holiday</th>
                <th>Type</th>
                <th>When</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className={editingId === row.id ? "is-active" : ""}>
                    <td>{row.name}</td>
                    <td>{holidayKindLabel(row.kind)}</td>
                    <td>{holidayWhen(row)}</td>
                    <td>
                      {canManage ? (
                        <div className="row-actions">
                          <IconButton label="Edit" onClick={() => openEdit(row)}><IconPencil /></IconButton>
                          <IconButton label="Delete" disabled={busy} onClick={() => void remove(row)}><IconTrash /></IconButton>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                  {mode === "edit" && editingId === row.id && !phoneList ? (
                    <tr className="titles-inline-form"><td colSpan={4}>{form}</td></tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
          <ul className="titles-list">
            {rows.map((row) => (
              <Fragment key={row.id}>
                <li className={editingId === row.id ? "titles-row is-active" : "titles-row"}>
                  <div className="titles-row-top">
                    <div className="titles-main">
                      <strong>{row.name}</strong>
                      <span>{holidayKindLabel(row.kind)} · {holidayWhen(row)}</span>
                    </div>
                  </div>
                  {canManage ? (
                    <div className="row-actions">
                      <button className="btn ghost small" type="button" onClick={() => openEdit(row)}>Edit</button>
                      <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(row)}>Delete</button>
                    </div>
                  ) : null}
                </li>
                {mode === "edit" && editingId === row.id && phoneList ? (
                  <li className="titles-inline-form">{form}</li>
                ) : null}
              </Fragment>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
