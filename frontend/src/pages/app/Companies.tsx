import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { LeaveTypes } from "../../components/LeaveTypes";
import { IconPlus } from "../../components/icons";
import type { Branch, Company, Country, LeaveType } from "../../types";
import { EmptyState, FormSkeleton, matchesSearch, PageHeader, SearchField, StatusPill, TableSkeleton } from "../../ui";

type CompanyForm = {
  name: string;
  legal_name: string;
  registration_number: string;
  email: string;
  phone: string;
  website: string;
  status: string;
};

const emptyCompany: CompanyForm = {
  name: "",
  legal_name: "",
  registration_number: "",
  email: "",
  phone: "",
  website: "",
  status: "ACTIVE",
};

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function fromCompany(row: Company): CompanyForm {
  return {
    name: row.name,
    legal_name: row.legal_name ?? "",
    registration_number: row.registration_number ?? "",
    email: row.email ?? "",
    phone: row.phone ?? "",
    website: row.website ?? "",
    status: row.status,
  };
}

export default function CompaniesPage() {
  const {
    token,
    company,
    companies,
    allBranches,
    canManageOrg,
    hasPermission,
    setCompanyId,
    reloadOrg,
    notify,
  } = useWorkspace();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [editing, setEditing] = useState<Company | null>(null);
  const [form, setForm] = useState<CompanyForm>(emptyCompany);
  const [withHq, setWithHq] = useState(true);
  const [hqName, setHqName] = useState("Head Office");
  const [hqCode, setHqCode] = useState("HQ");
  const [hqCountryId, setHqCountryId] = useState("");
  const [countries, setCountries] = useState<Country[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [leaveLoading, setLeaveLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api<Country[]>("/countries").then((rows) => {
      setCountries(rows);
      setHqCountryId((current) => current || rows[0]?.id || "");
    }).catch(() => undefined).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!company || !token) {
      setLeaveTypes([]);
      return;
    }
    setLeaveLoading(true);
    api<LeaveType[]>(`/leave-types?company_id=${company.id}`, { token })
      .then(setLeaveTypes)
      .catch(() => setLeaveTypes([]))
      .finally(() => setLeaveLoading(false));
  }, [company?.id, token]);

  const branchCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of allBranches) {
      counts.set(row.company_id, (counts.get(row.company_id) ?? 0) + 1);
    }
    return counts;
  }, [allBranches]);

  function selectCompany(row: Company) {
    setCompanyId(row.id);
  }

  function viewBranches(row: Company) {
    setCompanyId(row.id);
    navigate("/app/branches");
  }

  const selectedBranches = allBranches.filter((row) => row.company_id === company?.id);
  const visible = useMemo(
    () => companies.filter((row) => matchesSearch(query, row.name, row.legal_name, row.email, row.registration_number, row.phone)),
    [companies, query],
  );

  function startCreate() {
    setMode("create");
    setEditing(null);
    setForm(emptyCompany);
    setWithHq(true);
    setHqName("Head Office");
    setHqCode("HQ");
    setError(null);
  }

  function startEdit(row: Company) {
    setMode("edit");
    setEditing(row);
    setForm(fromCompany(row));
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canManageOrg) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        name: form.name.trim(),
        legal_name: blankToNull(form.legal_name),
        registration_number: blankToNull(form.registration_number),
        email: blankToNull(form.email),
        phone: blankToNull(form.phone),
        website: blankToNull(form.website),
        status: form.status,
      };
      if (mode === "create") {
        const created = await api<Company>("/companies", {
          method: "POST",
          token,
          body: JSON.stringify(payload),
        });
        let createdBranch: Branch | undefined;
        if (withHq) {
          if (!hqCountryId) throw new Error("Select a country for the head office.");
          createdBranch = await api<Branch>("/branches", {
            method: "POST",
            token,
            body: JSON.stringify({
              company_id: created.id,
              country_id: hqCountryId,
              name: hqName.trim() || "Head Office",
              code: hqCode.trim().toUpperCase() || "HQ",
            }),
          });
        }
        await reloadOrg({ companyId: created.id, branchId: createdBranch?.id });
        notify(`${created.name} added to this workspace.`);
      } else if (editing) {
        await api<Company>(`/companies/${editing.id}`, {
          method: "PATCH",
          token,
          body: JSON.stringify(payload),
        });
        await reloadOrg({ companyId: editing.id });
        notify("Company updated.");
      }
      setMode("idle");
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save company");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(row: Company) {
    if (!canManageOrg) return;
    setBusy(true);
    try {
      await api<Company>(`/companies/${row.id}`, {
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
        title="Companies"
        description="Legal entities in this workspace. Switching a company scopes people, payroll, leave types, and branches to that entity."
        actions={
          canManageOrg ? (
            <button className="btn small" type="button" onClick={startCreate}><IconPlus /> Add company</button>
          ) : null
        }
      />

      <div className="filters" style={{ marginBottom: 14 }}>
        <SearchField value={query} onChange={setQuery} placeholder="Name, legal name, or email" />
      </div>

      {loading ? (
        <div className="grid-2">
          <section className="card"><TableSkeleton cols={4} /></section>
          <section className="card card-pad"><FormSkeleton compact fields={6} /></section>
        </div>
      ) : (
      <div className="grid-2">
        <section className="card">
          {visible.length === 0 ? (
            <EmptyState
              title={query.trim() ? "No matching companies" : "No companies"}
              note={query.trim() ? `Nothing matched “${query.trim()}”.` : "Your first company is created at signup."}
              action={!query.trim() && canManageOrg ? <button className="btn small" type="button" onClick={startCreate}>Add company</button> : null}
            />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Branches</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr
                    key={row.id}
                    className={row.id === company?.id ? "is-active is-clickable" : "is-clickable"}
                    onClick={() => selectCompany(row)}
                  >
                    <td data-label="Company">
                      <strong>{row.name}</strong>
                      <div className="muted">{row.legal_name || row.email || "—"}</div>
                    </td>
                    <td data-label="Branches">{branchCounts.get(row.id) ?? 0}</td>
                    <td data-label="Status"><StatusPill value={row.status} /></td>
                    <td>
                      <div className="row-actions" onClick={(event) => event.stopPropagation()}>
                        <button className="btn small" type="button" onClick={() => viewBranches(row)}>View branches</button>
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
            company ? (
              <>
                <div className="page-head" style={{ marginBottom: 12 }}>
                  <div>
                    <h3 style={{ fontSize: "1rem", margin: 0 }}>{company.name}</h3>
                    <p>Branches for this company. Click another row to switch.</p>
                  </div>
                </div>
                {selectedBranches.length === 0 ? (
                  <EmptyState
                    title="No branches yet"
                    note="This company has no sites."
                    action={<Link className="btn small" to="/app/branches">Add a branch</Link>}
                  />
                ) : (
                  <table>
                    <thead>
                      <tr><th>Branch</th><th>Code</th><th>Status</th></tr>
                    </thead>
                    <tbody>
                      {selectedBranches.map((row) => (
                        <tr key={row.id}>
                          <td data-label="Branch">{row.name}</td>
                          <td data-label="Code">{row.code}</td>
                          <td data-label="Status"><StatusPill value={row.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="actions" style={{ marginTop: 12 }}>
                  <button className="btn" type="button" onClick={() => viewBranches(company)}>Open branches</button>
                </div>
              </>
            ) : (
              <EmptyState title="Select a company" note="Click a company in the list to see its branches." />
            )
          ) : (
            <form onSubmit={onSubmit}>
              <h3 style={{ margin: 0, fontSize: "1rem" }}>{mode === "create" ? "New company" : "Edit company"}</h3>
              <div className="form-grid">
                <label>Name <span className="req">*</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
                <label>Legal name<input value={form.legal_name} onChange={(event) => setForm({ ...form, legal_name: event.target.value })} /></label>
                <label>Registration no.<input value={form.registration_number} onChange={(event) => setForm({ ...form, registration_number: event.target.value })} /></label>
                <label>Status
                  <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                    <option value="ACTIVE">Active</option>
                    <option value="INACTIVE">Inactive</option>
                  </select>
                </label>
                <label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
                <label>Phone<input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label>
                <label style={{ gridColumn: "1 / -1" }}>Website<input value={form.website} onChange={(event) => setForm({ ...form, website: event.target.value })} /></label>
              </div>
              {mode === "create" ? (
                <div className="nested-block">
                  <label style={{ fontWeight: 600 }}>
                    <input type="checkbox" checked={withHq} onChange={(event) => setWithHq(event.target.checked)} />
                    {" "}Create a head office branch now
                  </label>
                  {withHq ? (
                    <div className="form-grid" style={{ marginTop: 10 }}>
                      <label>Branch name<input value={hqName} onChange={(event) => setHqName(event.target.value)} /></label>
                      <label>Code<input value={hqCode} onChange={(event) => setHqCode(event.target.value)} /></label>
                      <label style={{ gridColumn: "1 / -1" }}>
                        Country
                        <select required={withHq} value={hqCountryId} onChange={(event) => setHqCountryId(event.target.value)}>
                          {countries.map((country) => (
                            <option key={country.id} value={country.id}>{country.name}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                  ) : null}
                </div>
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
      {company && !loading ? (
        <section className="card" style={{ marginTop: 16 }}>
          {leaveLoading ? (
            <div className="card-pad"><FormSkeleton compact fields={4} /></div>
          ) : (
            <LeaveTypes
              token={token}
              apiBase=""
              companyId={company.id}
              title={`Leave types · ${company.name}`}
              rows={leaveTypes}
              canManage={hasPermission("leave.manage")}
              onChange={setLeaveTypes}
            />
          )}
        </section>
      ) : null}
    </>
  );
}
