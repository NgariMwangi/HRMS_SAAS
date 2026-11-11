import { FormEvent, useEffect, useMemo, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { IconPlus } from "../../components/icons";
import type { Branch, Country } from "../../types";
import { EmptyState, FormSkeleton, matchesSearch, PageHeader, SearchField, StatusPill, TableSkeleton } from "../../ui";

type BranchForm = {
  name: string;
  code: string;
  country_id: string;
  city: string;
  state: string;
  postal_code: string;
  address: string;
  timezone: string;
  status: string;
};

const emptyBranch: BranchForm = {
  name: "",
  code: "",
  country_id: "",
  city: "",
  state: "",
  postal_code: "",
  address: "",
  timezone: "",
  status: "ACTIVE",
};

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function fromBranch(row: Branch): BranchForm {
  return {
    name: row.name,
    code: row.code,
    country_id: row.country_id ?? "",
    city: row.city ?? "",
    state: row.state ?? "",
    postal_code: row.postal_code ?? "",
    address: row.address ?? "",
    timezone: row.timezone ?? "",
    status: row.status,
  };
}

export default function BranchesPage() {
  const {
    token,
    company,
    companies,
    branch,
    branches,
    canManageOrg,
    setCompanyId,
    setBranchId,
    reloadOrg,
    notify,
  } = useWorkspace();
  const [countries, setCountries] = useState<Country[]>([]);
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [editing, setEditing] = useState<Branch | null>(null);
  const [form, setForm] = useState<BranchForm>(emptyBranch);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setQuery("");
  }, [company?.id]);

  useEffect(() => {
    setLoading(true);
    api<Country[]>("/countries").then((rows) => {
      setCountries(rows);
      setForm((current) => ({ ...current, country_id: current.country_id || rows[0]?.id || "" }));
    }).catch(() => undefined).finally(() => setLoading(false));
  }, []);

  const countryById = useMemo(
    () => new Map(countries.map((row) => [row.id, row])),
    [countries],
  );

  const selectedCountry = countryById.get(form.country_id);
  const visible = useMemo(
    () => branches.filter((row) => matchesSearch(query, row.name, row.code, row.city, row.state, countryById.get(row.country_id ?? "")?.name)),
    [branches, query, countryById],
  );

  function startCreate() {
    setMode("create");
    setEditing(null);
    setForm({
      ...emptyBranch,
      country_id: countries[0]?.id ?? "",
      status: "ACTIVE",
    });
    setError(null);
  }

  function startEdit(row: Branch) {
    setMode("edit");
    setEditing(row);
    setForm(fromBranch(row));
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
        code: form.code.trim().toUpperCase(),
        country_id: form.country_id,
        city: blankToNull(form.city),
        state: blankToNull(form.state),
        postal_code: blankToNull(form.postal_code),
        address: blankToNull(form.address),
        timezone: blankToNull(form.timezone),
        status: form.status,
      };
      if (mode === "create") {
        const created = await api<Branch>("/branches", {
          method: "POST",
          token,
          body: JSON.stringify({ ...payload, company_id: company.id }),
        });
        await reloadOrg({ companyId: company.id, branchId: created.id });
        notify(`${created.name} added to ${company.name}.`);
      } else if (editing) {
        await api<Branch>(`/branches/${editing.id}`, {
          method: "PATCH",
          token,
          body: JSON.stringify(payload),
        });
        await reloadOrg({ companyId: company.id, branchId: editing.id });
        notify("Branch updated.");
      }
      setMode("idle");
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save branch");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(row: Branch) {
    if (!canManageOrg) return;
    setBusy(true);
    try {
      await api<Branch>(`/branches/${row.id}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({ status: row.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }),
      });
      await reloadOrg();
      notify(row.status === "ACTIVE" ? `${row.name} marked inactive.` : `${row.name} reactivated.`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not update status");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Branches"
        description="Sites for the company selected below. Country on a branch sets timezone and currency."
        actions={
          canManageOrg && company ? (
            <button className="btn small" type="button" onClick={startCreate}><IconPlus /> Add branch</button>
          ) : null
        }
      />
      <div className="filters" style={{ marginBottom: 14 }}>
        <SearchField value={query} onChange={setQuery} placeholder="Name, code, or city" />
        <label>
          Company
          <select
            value={company?.id ?? ""}
            onChange={(event) => setCompanyId(event.target.value)}
          >
            {companies.length === 0 ? <option value="">No companies</option> : null}
            {companies.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <div className="grid-2">
          <section className="card"><TableSkeleton cols={5} /></section>
          <section className="card card-pad"><FormSkeleton compact fields={6} /></section>
        </div>
      ) : (
      <div className="grid-2">
        <section className="card">
          {visible.length === 0 ? (
            <EmptyState
              title={query.trim() ? "No matching branches" : "No branches"}
              note={query.trim() ? `Nothing matched “${query.trim()}”.` : "Head office is usually created at signup. Add another site for this company."}
              action={!query.trim() && canManageOrg && company ? <button className="btn small" type="button" onClick={startCreate}>Add branch</button> : null}
            />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Branch</th>
                  <th>Country</th>
                  <th>City</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.id} className={row.id === branch?.id ? "is-active" : ""}>
                    <td data-label="Branch">
                      <strong>{row.name}</strong>
                      {row.timezone ? <div className="muted">{row.timezone}</div> : null}
                    </td>
                    <td data-label="Country">{countryById.get(row.country_id ?? "")?.name ?? "—"}</td>
                    <td data-label="City">{row.city ?? "—"}</td>
                    <td data-label="Status"><StatusPill value={row.status} /></td>
                    <td>
                      <div className="row-actions">
                        {row.id !== branch?.id ? (
                          <button className="btn ghost small" type="button" onClick={() => setBranchId(row.id)}>Use</button>
                        ) : (
                          <span className="muted">Current</span>
                        )}
                        {canManageOrg ? (
                          <>
                            <button className="btn ghost small" type="button" onClick={() => startEdit(row)}>Edit</button>
                            <button className="btn ghost small" type="button" disabled={busy} onClick={() => toggleStatus(row)}>
                              {row.status === "ACTIVE" ? "Deactivate" : "Activate"}
                            </button>
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card card-pad">
          {mode === "idle" ? (
            <EmptyState
              title={branch ? branch.name : "Select a branch"}
              note="Use a branch to work in that site, or add another location for this company."
            />
          ) : (
            <form onSubmit={onSubmit}>
              <h3 style={{ margin: 0, fontSize: "1rem" }}>{mode === "create" ? "New branch" : "Edit branch"}</h3>
              <div className="form-grid">
                <label>Name <span className="req">*</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
                <label>Code <span className="req">*</span><input required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></label>
                <label>Country
                  <select required value={form.country_id} onChange={(event) => setForm({ ...form, country_id: event.target.value, timezone: "" })}>
                    <option value="">Select</option>
                    {countries.map((country) => (
                      <option key={country.id} value={country.id}>{country.name}</option>
                    ))}
                  </select>
                </label>
                <label>Status
                  <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                    <option value="ACTIVE">Active</option>
                    <option value="INACTIVE">Inactive</option>
                  </select>
                </label>
                <label>City<input value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} /></label>
                <label>State / region<input value={form.state} onChange={(event) => setForm({ ...form, state: event.target.value })} /></label>
                <label>Postal code<input value={form.postal_code} onChange={(event) => setForm({ ...form, postal_code: event.target.value })} /></label>
                <label>Timezone
                  <input
                    placeholder={selectedCountry?.default_timezone ?? "From country"}
                    value={form.timezone}
                    onChange={(event) => setForm({ ...form, timezone: event.target.value })}
                  />
                </label>
                <label style={{ gridColumn: "1 / -1" }}>Address<textarea value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
              </div>
              {selectedCountry ? (
                <p className="muted">
                  {selectedCountry.name} defaults to {selectedCountry.default_timezone ?? "the country timezone"}
                  {selectedCountry.default_currency ? ` · ${selectedCountry.default_currency.code}` : ""}.
                  Statutory payroll stays on the server.
                </p>
              ) : null}
              {error ? <p className="error">{error}</p> : null}
              <div className="actions">
                <button className="btn ghost" type="button" onClick={() => { setMode("idle"); setEditing(null); }}>Cancel</button>
                <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              </div>
            </form>
          )}
        </section>
      </div>
      )}
    </>
  );
}
