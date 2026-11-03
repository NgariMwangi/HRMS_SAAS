import { FormEvent, useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import type { BenefitType } from "../types";
import { EmptyState, FormSkeleton, StatusPill, formatMoney } from "../ui";

type Draft = {
  name: string;
  default_amount: string;
  is_active: boolean;
};

const emptyDraft = (): Draft => ({ name: "", default_amount: "", is_active: true });

const suggestions = ["Commission", "Bonus", "Overtime"];

export function BenefitTypes({
  token,
  apiBase = "",
  company,
  currency,
  canManage,
  notify,
}: {
  token: string;
  apiBase?: string;
  company: { id: string; name: string } | null;
  currency?: string | null;
  canManage: boolean;
  notify: (message: string) => void;
}) {
  const [rows, setRows] = useState<BenefitType[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"closed" | "add" | "edit">("closed");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<BenefitType[]>(apiUrl(apiBase, `/benefit-types?company_id=${company.id}`), { token })
      .then((list) => {
        setRows(list);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [company?.id, token, apiBase]);

  function openAdd(name = "") {
    setMode("add");
    setEditingId(null);
    setDraft({ ...emptyDraft(), name });
    setError(null);
  }

  function openEdit(row: BenefitType) {
    setMode("edit");
    setEditingId(row.id);
    setDraft({ name: row.name, default_amount: row.default_amount ?? "", is_active: row.is_active });
    setError(null);
  }

  function sortRows(list: BenefitType[]) {
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!company || !canManage) return;
    setBusy(true);
    setError(null);
    const body = {
      name: draft.name.trim(),
      default_amount: draft.default_amount || null,
      is_active: draft.is_active,
    };
    try {
      if (mode === "edit" && editingId) {
        const saved = await api<BenefitType>(apiUrl(apiBase, `/benefit-types/${editingId}`), {
          method: "PATCH",
          token,
          body: JSON.stringify(body),
        });
        setRows((current) => sortRows(current.map((row) => (row.id === saved.id ? saved : row))));
        notify("Benefit type updated.");
      } else {
        const saved = await api<BenefitType>(apiUrl(apiBase, "/benefit-types"), {
          method: "POST",
          token,
          body: JSON.stringify({ ...body, company_id: company.id }),
        });
        setRows((current) => sortRows([...current, saved]));
        notify("Benefit type added.");
      }
      setMode("closed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save benefit type");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: BenefitType) {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      await api(apiUrl(apiBase, `/benefit-types/${row.id}`), { method: "DELETE", token });
      setRows((current) => current.filter((item) => item.id !== row.id));
      notify("Benefit type deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete benefit type");
    } finally {
      setBusy(false);
    }
  }

  if (!company) return null;

  const missing = suggestions.filter((name) => !rows.some((row) => row.name.toLowerCase() === name.toLowerCase()));

  return (
    <section className="card" style={{ marginTop: "1rem" }}>
      <div className="card-head">
        <div>
          <h3>Benefits</h3>
          <p>
            Extra earnings such as commission, bonus or overtime. They are added to gross pay, so PAYE, NSSF, SHIF and
            housing levy apply. Assign them to people on each employee's Salary page.
          </p>
        </div>
        {canManage && mode === "closed" ? (
          <button className="btn small" type="button" onClick={() => openAdd()} style={{ flexShrink: 0 }}>
            Add benefit type
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
                placeholder="e.g. Commission, Bonus, Overtime"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </label>
            <label>
              Default amount
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

      {error ? <p className="error" style={{ margin: "0.75rem 1.1rem 0" }}>{error}</p> : null}

      {loading ? (
        <div className="card-pad"><FormSkeleton compact fields={2} /></div>
      ) : rows.length === 0 ? (
        <EmptyState title="No benefit types yet" note="Add the commissions, bonuses and other earnings your payroll pays." />
      ) : (
        <table className="org-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Default amount</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Name">{row.name}</td>
                <td data-label="Default amount">
                  {row.default_amount ? formatMoney(row.default_amount, currency) : <span className="muted">—</span>}
                </td>
                <td data-label="Status"><StatusPill value={row.is_active ? "ACTIVE" : "INACTIVE"} /></td>
                <td className="row-actions">
                  {canManage ? (
                    <>
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

      {canManage && mode === "closed" && !loading && missing.length ? (
        <p className="muted card-pad" style={{ margin: 0, display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
          Quick add:
          {missing.map((name) => (
            <button key={name} className="btn ghost small" type="button" onClick={() => openAdd(name)}>
              {name}
            </button>
          ))}
        </p>
      ) : null}
    </section>
  );
}
