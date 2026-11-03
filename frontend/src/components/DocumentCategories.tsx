import { FormEvent, useState } from "react";
import { api } from "../api";
import type { DocumentCategory } from "../types";
import { IconPencil, IconTrash } from "./icons";
import { EmptyState, IconButton } from "../ui";

export function DocumentCategories({
  token,
  apiBase,
  companyId,
  rows,
  canManage,
  onChange,
}: {
  token: string;
  apiBase: string;
  companyId: string;
  rows: DocumentCategory[];
  canManage: boolean;
  onChange: (rows: DocumentCategory[]) => void;
}) {
  const [name, setName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<DocumentCategory>(`${apiBase}/document-categories`, {
        method: "POST",
        token,
        body: JSON.stringify({ company_id: companyId, name: name.trim() }),
      });
      onChange([...rows, saved].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)));
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add category");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !editingId || !editName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<DocumentCategory>(`${apiBase}/document-categories/${editingId}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({ name: editName.trim() }),
      });
      onChange(rows.map((row) => (row.id === saved.id ? saved : row)));
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update category");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: DocumentCategory) {
    if (!canManage || row.locked) return;
    setBusy(true);
    setError(null);
    try {
      await api(`${apiBase}/document-categories/${row.id}`, { method: "DELETE", token });
      onChange(rows.filter((item) => item.id !== row.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete category");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>
        These labels group employee files. Lifecycle is required and cannot be renamed or removed.
      </p>
      {rows.length === 0 ? (
        <EmptyState title="No categories" note="Add Personal, Academic, or another label this company uses." />
      ) : (
        <table>
          <thead><tr><th>Category</th><th></th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Category">
                  {editingId === row.id ? (
                    <form onSubmit={saveEdit} className="row-actions" style={{ justifyContent: "flex-start" }}>
                      <input required value={editName} onChange={(event) => setEditName(event.target.value)} />
                      <button className="btn small" type="submit" disabled={busy}>Save</button>
                      <button className="btn ghost small" type="button" onClick={() => setEditingId(null)}>Cancel</button>
                    </form>
                  ) : (
                    <>
                      <strong>{row.name}</strong>
                      {row.locked ? <div className="muted">Locked — files from lifecycle actions</div> : null}
                    </>
                  )}
                </td>
                <td className="row-actions">
                  {canManage && !row.locked && editingId !== row.id ? (
                    <>
                      <IconButton
                        label="Edit"
                        onClick={() => { setEditingId(row.id); setEditName(row.name); setError(null); }}
                      >
                        <IconPencil />
                      </IconButton>
                      <IconButton label="Delete" disabled={busy} onClick={() => void remove(row)}>
                        <IconTrash />
                      </IconButton>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage ? (
        <form onSubmit={create} className="actions" style={{ marginTop: 12 }}>
          <input required placeholder="New category" value={name} onChange={(event) => setName(event.target.value)} />
          <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Add category"}</button>
        </form>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
