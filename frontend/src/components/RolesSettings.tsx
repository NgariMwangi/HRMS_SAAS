import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { useWorkspace } from "../context/WorkspaceContext";
import type { AccessRole, Permission, User } from "../types";
import { Card, FormSkeleton, StatusPill } from "../ui";

export default function RolesSettings() {
  const workspace = useWorkspace();
  return <RolesBoard user={workspace.user} canManage={workspace.hasPermission("access.manage_roles")} notify={workspace.notify} reloadAccess={workspace.reloadAccess} />;
}

export function RolesBoard({ user, canManage, notify, reloadAccess, apiBase = "/access", token }: { user: { id: string; role: string }; canManage: boolean; notify: (message: string) => void; reloadAccess?: () => Promise<{ permissions: string[] }>; apiBase?: string; token?: string }) {
  const [roles, setRoles] = useState<AccessRole[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [catalog, setCatalog] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AccessRole | "new" | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  async function load() {
    const [roleRows, userRows, permissions] = await Promise.all([
      api<AccessRole[]>(`${apiBase}/roles`, { token }), api<User[]>(`${apiBase}/users`, { token }), api<Permission[]>(`${apiBase}/permissions`, { token }),
    ]);
    setRoles(roleRows); setUsers(userRows); setCatalog(permissions);
  }

  useEffect(() => {
    if (!canManage) { setLoading(false); return; }
    setLoading(true);
    load().catch((err: Error) => setError(err.message)).finally(() => setLoading(false));
  }, [canManage, apiBase, token]);

  function edit(role: AccessRole | "new") {
    setEditing(role); setError(null);
    setName(role === "new" ? "" : role.name);
    setDescription(role === "new" ? "" : role.description ?? "");
    setSelected(role === "new" ? [] : role.permissions);
  }

  async function mutate(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(null);
    try {
      await action();
      const access = reloadAccess ? await reloadAccess() : { permissions: ["access.manage_roles"] };
      if (access.permissions.includes("access.manage_roles")) await load();
      notify(message);
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save access"); return false; }
    finally { setBusy(false); }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing || !name.trim()) return;
    const ok = await mutate(() => api(editing === "new" ? `${apiBase}/roles` : `${apiBase}/roles/${editing.id}`, {
      token, method: editing === "new" ? "POST" : "PATCH",
      body: JSON.stringify({ name: name.trim(), description: description.trim() || null, permissions: selected }),
    }), "Role saved.");
    if (ok) setEditing(null);
  }

  if (!canManage) return <Card padded title="Roles & permissions"><p className="muted">Your role does not allow you to manage workspace access.</p></Card>;

  return <div className="stack">
    {error ? <p className="error" role="alert">{error}</p> : null}
    <Card padded title="Roles & permissions">
      <p className="muted">Roles apply across this workspace. Owners always have full access. Changes take effect on the next request.</p>
      <button className="btn small" type="button" disabled={busy} onClick={() => edit("new")}>Create role</button>
      {loading ? <FormSkeleton compact fields={4} /> : <div className="table-wrap"><table>
        <thead><tr><th>Role</th><th>Users</th><th>Permissions</th><th>Actions</th></tr></thead>
        <tbody>{roles.map((role) => <tr key={role.id}>
          <td data-label="Role"><strong>{role.name}</strong><div className="muted">{role.description}</div></td>
          <td data-label="Users">{role.user_count}</td>
          <td data-label="Permissions">{role.locked ? "Full access" : `${role.permissions.length} permissions`}</td>
          <td data-label="Actions"><div className="actions">
            {!role.locked ? <button className="btn ghost small" type="button" disabled={busy} onClick={() => edit(role)}>Edit</button> : <span className="muted">Protected</span>}
            {!role.is_system ? <button className="btn ghost small" type="button" disabled={busy || role.user_count > 0} onClick={() => {
              if (window.confirm(`Delete the unused role “${role.name}”?`)) void mutate(() => api(`${apiBase}/roles/${role.id}`, { token, method: "DELETE" }), "Role deleted.");
            }}>Delete</button> : null}
          </div></td>
        </tr>)}</tbody>
      </table></div>}
    </Card>
    {editing ? <form className="card card-pad" onSubmit={save}>
      <h3>{editing === "new" ? "Create role" : `Edit ${editing.name}`}</h3>
      <div className="form-grid">
        <label>Role name<input required maxLength={80} value={name} onChange={(event) => setName(event.target.value)} disabled={busy} /></label>
        <label>Description<input maxLength={255} value={description} onChange={(event) => setDescription(event.target.value)} disabled={busy} /></label>
      </div>
      {[...new Set(catalog.map((item) => item.group))].map((group) => <fieldset key={group} disabled={busy} style={{ margin: "16px 0", border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}>
        <legend>{group}</legend>
        {catalog.filter((item) => item.group === group).map((item) => <label key={item.key} style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0" }}>
          <input type="checkbox" style={{ width: "auto" }} checked={selected.includes(item.key)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, item.key] : current.filter((key) => key !== item.key))} />{item.label}
        </label>)}
      </fieldset>)}
      <div className="actions"><button className="btn" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save role"}</button><button className="btn ghost" type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button></div>
    </form> : null}
    <Card title="User access">
      <div className="table-wrap"><table><thead><tr><th>User</th><th>Status</th><th>Role</th></tr></thead>
        <tbody>{users.map((person) => <tr key={person.id}>
          <td data-label="User"><strong>{person.full_name}</strong><div className="muted">{person.email}{person.id === user.id ? " · You" : ""}</div></td>
          <td data-label="Status"><StatusPill value={person.status} /></td>
          <td data-label="Role"><select aria-label={`Role for ${person.full_name}`} value={person.role} disabled={busy || (person.role === "OWNER" && user.role !== "OWNER")} onChange={(event) => {
            const role = event.target.value;
            void mutate(() => api(`${apiBase}/users/${person.id}`, { token, method: "PATCH", body: JSON.stringify({ role }) }), "User role updated.");
          }}>{roles.filter((role) => role.key !== "OWNER" || user.role === "OWNER" || person.role === "OWNER").map((role) => <option key={role.key} value={role.key}>{role.name}</option>)}</select></td>
        </tr>)}</tbody>
      </table></div>
    </Card>
  </div>;
}
