import CompanyDomains from "../components/CompanyDomains";
import { FormEvent, lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { adminSession, adminToken, api, apiDownload, viewDocument } from "../api";
import { DocumentPreview } from "../components/DocumentPreview";
import type {
  AccessRole,
  Branch,
  Company,
  Country,
  Department,
  Employee,
  JobTitle,
  PublicHoliday,
  TenantWorkspace,
  User,
} from "../types";
import { documentDownloadPath, documentFileType, employeeName, formatFileSize, groupDocumentsByCategory, nextOfKinError, nextOfKinFromRow, nextOfKinPayload, type CompanyDocument, type NextOfKin, type NextOfKinDraft, type Supervisor } from "../types";
import { DocumentCategories } from "../components/DocumentCategories";
import { AttendanceRegister } from "./app/Attendance";
import { LifecycleBoard } from "./app/Lifecycle";
import { PayrollBoard } from "./app/Payroll";
import { PayrollSettingsForm } from "./app/PayrollSettings";
import { LeaveBalances } from "../components/LeaveBalances";
import { LeaveRequests } from "../components/LeaveRequests";
import { LeaveTypes } from "../components/LeaveTypes";
import { NextOfKinFields } from "../components/NextOfKinFields";
import { PublicHolidays } from "../components/PublicHolidays";
import { SupervisorFields } from "../components/SupervisorFields";
import { IconDownload, IconEye } from "../components/icons";
import { Avatar, Card, EmptyState, IconButton, matchesSearch, PageSkeleton, PersonCell, SearchField, StatusPill, formatDate } from "../ui";

const TIERS = ["TRIAL", "STARTER", "GROWTH", "ENTERPRISE"];
const AdminModuleOversight = lazy(() => import("../components/AdminModuleOversight"));
const AdminGeneralReports = lazy(() => import("../components/AdminGeneralReports"));
const AdminRoles = lazy(() => import("../components/RolesSettings").then(m => ({ default: m.RolesBoard })));
const STATUSES = ["ACTIVE", "INACTIVE"];
const EMPLOYMENT = ["FULL_TIME", "CONTRACT", "INTERN", "PROBATION"];

type Tab = "overview" | "companies" | "branches" | "departments" | "titles" | "employees" | "users" | "documents" | "leave" | "attendance" | "payroll" | "lifecycle" | "performance" | "recruitment" | "reports" | "access" | "domains" | "more";
const TABS: [Tab, string][] = [
  ["overview", "Overview"],
  ["companies", "Companies"],
  ["branches", "Branches"],
  ["departments", "Departments"],
  ["titles", "Job titles"],
  ["employees", "Employees"],
  ["users", "Users"],
  ["access", "Roles & permissions"],
  ["documents", "Documents"],
  ["leave", "Leave"],
  ["attendance", "Attendance"],
  ["payroll", "Payroll"],
  ["lifecycle", "Lifecycle"],
  ["performance", "Performance"],
  ["recruitment", "Recruitment"],
  ["reports", "Reports"],
  ["domains", "Company domains"],
  ["more", "Connections"],
];

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export default function AdminTenantDetail() {
  const { tenantId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = adminToken.get();
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<TenantWorkspace | null>(null);
  const [roles, setRoles] = useState<AccessRole[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [listQuery, setListQuery] = useState("");
  const [docFiles, setDocFiles] = useState<CompanyDocument[]>([]);
  const [docCompanyId, setDocCompanyId] = useState("");
  const [opsCompanyId, setOpsCompanyId] = useState("");
  const [opsBranchId, setOpsBranchId] = useState("");
  const [leaveSection, setLeaveSection] = useState<"Requests" | "Balances" | "Types" | "Holidays">("Requests");
  const [payrollSection, setPayrollSection] = useState<"runs" | "settings">("runs");
  const [holidays, setHolidays] = useState<PublicHoliday[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [docCategory, setDocCategory] = useState("");
  const [viewingDoc, setViewingDoc] = useState<CompanyDocument | null>(null);

  async function load() {
    if (!token || !tenantId) return;
    const [workspace, countryRows, roleRows] = await Promise.all([
      api<TenantWorkspace>(`/platform/tenants/${tenantId}/workspace`, { token }),
      api<Country[]>("/platform/countries", { token }),
      api<AccessRole[]>(`/platform/tenants/${tenantId}/modules/access/roles`, { token }),
    ]);
    setData(workspace);
    setCountries(countryRows);
    setRoles(roleRows);
  }

  useEffect(() => {
    if (!token) {
      navigate("/admin/login");
      return;
    }
    load().catch((err: Error) => setError(err.message));
  }, [navigate, token, tenantId]);

  useEffect(() => {
    const next = searchParams.get("tab");
    if (next && TABS.some(([id]) => id === next)) {
      setTab(next as Tab);
    }
  }, [searchParams]);

  useEffect(() => {
    setListQuery("");
  }, [tab]);

  const companiesById = useMemo(() => {
    const map = new Map<string, Company>();
    data?.companies.forEach((row) => map.set(row.id, row));
    return map;
  }, [data]);
  const departmentsById = useMemo(() => {
    const map = new Map<string, Department>();
    data?.departments.forEach((row) => map.set(row.id, row));
    return map;
  }, [data]);
  const visibleCompanies = useMemo(
    () => (data?.companies ?? []).filter((row) => matchesSearch(listQuery, row.name, row.legal_name, row.email, row.registration_number)),
    [data, listQuery],
  );
  const visibleBranches = useMemo(
    () => (data?.branches ?? []).filter((row) => matchesSearch(listQuery, row.name, row.code, row.city, companiesById.get(row.company_id)?.name)),
    [data, listQuery, companiesById],
  );
  const visibleDepartments = useMemo(
    () => (data?.departments ?? []).filter((row) => matchesSearch(listQuery, row.name, row.code, row.description, companiesById.get(row.company_id)?.name)),
    [data, listQuery, companiesById],
  );
  const visibleTitles = useMemo(
    () => (data?.job_titles ?? []).filter((row) => matchesSearch(
      listQuery,
      row.name,
      row.code,
      companiesById.get(row.company_id)?.name,
      row.department_id ? departmentsById.get(row.department_id)?.name : "Company-wide",
    )),
    [data, listQuery, companiesById, departmentsById],
  );
  const visibleEmployees = useMemo(
    () => (data?.employees ?? []).filter((row) => matchesSearch(listQuery, employeeName(row), row.employee_number, row.email, row.personal_email, row.id_number, row.nssf_no, row.shif_no)),
    [data, listQuery],
  );
  const visibleUsers = useMemo(
    () => (data?.users ?? []).filter((row) => matchesSearch(listQuery, row.full_name, row.email, row.role)),
    [data, listQuery],
  );
  const visibleDocFiles = useMemo(
    () => docFiles.filter((row) => {
      if (docCategory && row.category_id !== docCategory) return false;
      return matchesSearch(listQuery, row.employee_name, row.employee_number, row.filename, row.category, row.event_label);
    }),
    [docFiles, docCategory, listQuery],
  );
  const docGroups = useMemo(
    () => groupDocumentsByCategory(
      visibleDocFiles,
      (data?.document_categories ?? []).filter((row) => row.company_id === docCompanyId),
    ),
    [visibleDocFiles, data, docCompanyId],
  );
  useEffect(() => {
    if (!data?.companies.length) return;
    setDocCompanyId((current) => current || data.companies[0].id);
    setOpsCompanyId((current) => current || data.companies[0].id);
  }, [data]);

  useEffect(() => {
    if (tab !== "documents" || !token || !tenantId || !docCompanyId) return;
    api<CompanyDocument[]>(`/platform/tenants/${tenantId}/documents?company_id=${docCompanyId}`, { token })
      .then(setDocFiles)
      .catch(() => setDocFiles([]));
  }, [tab, token, tenantId, docCompanyId]);

  useEffect(() => {
    if (!data) return;
    const branches = data.branches.filter((row) => row.company_id === opsCompanyId);
    setOpsBranchId((current) => (current && branches.some((row) => row.id === current) ? current : branches[0]?.id ?? ""));
  }, [data, opsCompanyId]);

  useEffect(() => {
    if ((tab !== "leave" && tab !== "attendance" && tab !== "payroll") || !token || !tenantId || !opsCompanyId) return;
    const query = `/platform/tenants/${tenantId}/public-holidays?company_id=${opsCompanyId}${opsBranchId ? `&branch_id=${opsBranchId}` : ""}`;
    api<PublicHoliday[]>(query, { token })
      .then(setHolidays)
      .catch(() => setHolidays([]));
  }, [tab, token, tenantId, opsCompanyId, opsBranchId]);

  async function request<T>(path: string, options: RequestInit = {}): Promise<T | undefined> {
    if (!token) return undefined;
    setBusy(true);
    setError(null);
    try {
      const result = await api<T>(path, { ...options, token });
      await load();
      setEditing(null);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  async function remove(path: string, label: string) {
    if (!window.confirm(`Delete this ${label}? This cannot be undone.`)) return;
    await request(path, { method: "DELETE" });
  }

  if (!data || !tenantId) {
    if (error) return <p className="error">{error}</p>;
    return <PageSkeleton kpis rows={7} cols={5} />;
  }

  const tenant = data.tenant;
  const nextStatus = tenant.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
  const base = `/platform/tenants/${tenantId}`;
  const opsCompany = data.companies.find((row) => row.id === opsCompanyId) ?? data.companies[0] ?? null;
  const opsBranches = data.branches.filter((row) => row.company_id === opsCompany?.id);
  const opsBranch = opsBranches.find((row) => row.id === opsBranchId) ?? opsBranches[0] ?? null;
  const opsEmployees = data.employees.filter((row) => row.company_id === opsCompany?.id);
  const opsTypes = (data.leave_types ?? []).filter((row) => row.company_id === opsCompany?.id);

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow"><Link to="/admin/tenants">Tenants</Link></div>
          <div className="title-row">
            <h1>{tenant.name}</h1>
            <StatusPill value={tenant.status} />
            <StatusPill value={tenant.subscription_tier} />
          </div>
          <p>Manage every record in this workspace.</p>
        </div>
        <div className="actions">
          <select
            disabled={busy}
            value={tenant.subscription_tier}
            onChange={(event) => request(`${base}`, {
              method: "PATCH",
              body: JSON.stringify({ subscription_tier: event.target.value }),
            })}
          >
            {TIERS.map((tier) => <option key={tier} value={tier}>{tier}</option>)}
          </select>
          <button
            className="btn ghost small"
            type="button"
            disabled={busy}
            onClick={() => request(`${base}/extend-trial`, { method: "POST" })}
          >
            Extend trial
          </button>
          <button
            className={`btn small ${tenant.status === "ACTIVE" ? "warn" : ""}`}
            type="button"
            disabled={busy}
            onClick={() => request(`${base}`, {
              method: "PATCH",
              body: JSON.stringify({ status: nextStatus }),
            })}
          >
            {tenant.status === "ACTIVE" ? "Suspend" : "Restore"}
          </button>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {notice ? <p className="muted">{notice}</p> : null}

      <div className="filters"><label>Module<select value={tab} onChange={event => { setTab(event.target.value as Tab); setEditing(null); navigate(`/admin/tenants/${tenantId}?tab=${event.target.value}`); }}>{TABS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>

      {tab === "domains" && token && tenantId ? <><div className="filters"><label>Company<select value={opsCompanyId || data.companies[0]?.id || ""} onChange={event => setOpsCompanyId(event.target.value)}>{data.companies.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label></div>{data.companies.length ? <CompanyDomains key={opsCompanyId || data.companies[0].id} companyId={opsCompanyId || data.companies[0].id} token={token} apiBase={`/platform/tenants/${tenantId}/domains`} /> : <p className="muted">Create a company first.</p>}</> : null}
      {tab === "overview" ? (
        <>
          <div className="profile-hero">
            <div className="person">
              <Avatar name={tenant.name} size="lg" />
              <div>
                <div className="title-row">
                  <strong style={{ fontSize: "1.05rem" }}>{tenant.name}</strong>
                  <StatusPill value={tenant.status} />
                </div>
                <span>{tenant.subscription_tier.toLowerCase()} plan</span>
              </div>
            </div>
            <dl className="meta-grid">
              <div><dt>Created</dt><dd>{formatDate(tenant.created_at)}</dd></div>
              <div><dt>Trial ends</dt><dd>{formatDate(tenant.trial_ends_at)}</dd></div>
              <div><dt>Companies</dt><dd>{data.companies.length}</dd></div>
              <div><dt>Employees</dt><dd>{data.employees.length}</dd></div>
              <div><dt>Users</dt><dd>{data.users.length}</dd></div>
              <div><dt>Branches</dt><dd>{data.branches.length}</dd></div>
            </dl>
          </div>
          <Card title="Snapshot">
            <table>
              <thead><tr><th>Record</th><th>Count</th></tr></thead>
              <tbody>
                <tr><td data-label="Record">Companies</td><td data-label="Count">{data.companies.length}</td></tr>
                <tr><td data-label="Record">Branches</td><td data-label="Count">{data.branches.length}</td></tr>
                <tr><td data-label="Record">Departments</td><td data-label="Count">{data.departments.length}</td></tr>
                <tr><td data-label="Record">Job titles</td><td data-label="Count">{data.job_titles.length}</td></tr>
                <tr><td data-label="Record">Employees</td><td data-label="Count">{data.employees.length}</td></tr>
                <tr><td data-label="Record">Users</td><td data-label="Count">{data.users.length}</td></tr>
              </tbody>
            </table>
          </Card>
        </>
      ) : null}

      {tab === "companies" ? (
        <Card
          title="Companies"
          action={<button className="btn small" type="button" onClick={() => setEditing(editing === "new" ? null : "new")}>Add company</button>}
        >
          {editing === "new" ? (
            <CompanyForm
              busy={busy}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => request(`${base}/companies`, { method: "POST", body: JSON.stringify(body) })}
            />
          ) : null}
          {data.companies.length === 0 ? <EmptyState title="No companies" note="Add a company for this tenant." /> : (
            <>
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Name or email" />
            </div>
            {visibleCompanies.length === 0 ? (
              <EmptyState title="No matching companies" note={`Nothing matched “${listQuery.trim()}”.`} />
            ) : (
            <table>
              <thead><tr><th>Name</th><th>Email</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visibleCompanies.map((row) => (
                  <tr key={row.id}>
                    <td colSpan={editing === row.id ? 4 : undefined} data-label={editing === row.id ? undefined : "Name"}>
                      {editing === row.id ? (
                        <CompanyForm
                          initial={row}
                          busy={busy}
                          onCancel={() => setEditing(null)}
                          onSubmit={(body) => request(`${base}/companies/${row.id}`, { method: "PATCH", body: JSON.stringify(body) })}
                        />
                      ) : row.name}
                    </td>
                    {editing === row.id ? null : (
                      <>
                        <td data-label="Email">{row.email ?? "—"}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => setEditing(row.id)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(`${base}/companies/${row.id}`, "company and its records")}>Delete</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            </>
          )}
        </Card>
      ) : null}

      {tab === "branches" ? (
        <Card
          title="Branches"
          action={<button className="btn small" type="button" onClick={() => setEditing(editing === "new" ? null : "new")}>Add branch</button>}
        >
          {editing === "new" ? (
            <BranchForm
              companies={data.companies}
              countries={countries}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => request(`${base}/branches`, { method: "POST", body: JSON.stringify(body) })}
            />
          ) : null}
          {data.branches.length === 0 ? <EmptyState title="No branches" note="Add a branch under a company." /> : (
            <>
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Name, code, or company" />
            </div>
            {visibleBranches.length === 0 ? (
              <EmptyState title="No matching branches" note={`Nothing matched “${listQuery.trim()}”.`} />
            ) : (
            <table>
              <thead><tr><th>Branch</th><th>Company</th><th>Code</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visibleBranches.map((row) => (
                  <tr key={row.id}>
                    <td colSpan={editing === row.id ? 5 : undefined} data-label={editing === row.id ? undefined : "Branch"}>
                      {editing === row.id ? (
                        <BranchForm
                          initial={row}
                          companies={data.companies}
                          countries={countries}
                          busy={busy}
                          onCancel={() => setEditing(null)}
                          onSubmit={(body) => request(`${base}/branches/${row.id}`, { method: "PATCH", body: JSON.stringify(body) })}
                        />
                      ) : row.name}
                    </td>
                    {editing === row.id ? null : (
                      <>
                        <td data-label="Company">{companiesById.get(row.company_id)?.name ?? "—"}</td>
                        <td data-label="Code">{row.code}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => setEditing(row.id)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(`${base}/branches/${row.id}`, "branch")}>Delete</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            </>
          )}
        </Card>
      ) : null}

      {tab === "departments" ? (
        <Card
          title="Departments"
          action={<button className="btn small" type="button" onClick={() => setEditing(editing === "new" ? null : "new")}>Add department</button>}
        >
          {editing === "new" ? (
            <NamedOrgForm
              companies={data.companies}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => request(`${base}/departments`, { method: "POST", body: JSON.stringify(body) })}
            />
          ) : null}
          {data.departments.length === 0 ? <EmptyState title="No departments" note="Add a department under a company." /> : (
            <>
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Name, code, or company" />
            </div>
            {visibleDepartments.length === 0 ? (
              <EmptyState title="No matching departments" note={`Nothing matched “${listQuery.trim()}”.`} />
            ) : (
            <table>
              <thead><tr><th>Name</th><th>Company</th><th>Code</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visibleDepartments.map((row) => (
                  <tr key={row.id}>
                    <td colSpan={editing === row.id ? 5 : undefined} data-label={editing === row.id ? undefined : "Name"}>
                      {editing === row.id ? (
                        <NamedOrgForm
                          initial={row}
                          companies={data.companies}
                          hideCompany
                          busy={busy}
                          onCancel={() => setEditing(null)}
                          onSubmit={(body) => request(`${base}/departments/${row.id}`, { method: "PATCH", body: JSON.stringify(body) })}
                        />
                      ) : row.name}
                    </td>
                    {editing === row.id ? null : (
                      <>
                        <td data-label="Company">{companiesById.get(row.company_id)?.name ?? "—"}</td>
                        <td data-label="Code">{row.code ?? "—"}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => setEditing(row.id)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(`${base}/departments/${row.id}`, "department")}>Delete</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            </>
          )}
        </Card>
      ) : null}

      {tab === "titles" ? (
        <Card
          title="Job titles"
          action={<button className="btn small" type="button" onClick={() => setEditing(editing === "new" ? null : "new")}>Add job title</button>}
        >
          {editing === "new" ? (
            <JobTitleForm
              companies={data.companies}
              departments={data.departments}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => request(`${base}/job-titles`, { method: "POST", body: JSON.stringify(body) })}
            />
          ) : null}
          {data.job_titles.length === 0 ? <EmptyState title="No job titles" note="Add a role under a company." /> : (
            <>
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Title or company" />
            </div>
            {visibleTitles.length === 0 ? (
              <EmptyState title="No matching job titles" note={`Nothing matched “${listQuery.trim()}”.`} />
            ) : (
            <table>
              <thead><tr><th>Title</th><th>Company</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visibleTitles.map((row) => (
                  <tr key={row.id}>
                    <td colSpan={editing === row.id ? 4 : undefined} data-label={editing === row.id ? undefined : "Title"}>
                      {editing === row.id ? (
                        <JobTitleForm
                          initial={row}
                          companies={data.companies}
                          departments={data.departments}
                          busy={busy}
                          onCancel={() => setEditing(null)}
                          onSubmit={(body) => request(`${base}/job-titles/${row.id}`, { method: "PATCH", body: JSON.stringify(body) })}
                        />
                      ) : row.name}
                    </td>
                    {editing === row.id ? null : (
                      <>
                        <td data-label="Company">{companiesById.get(row.company_id)?.name ?? "—"}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => setEditing(row.id)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(`${base}/job-titles/${row.id}`, "job title")}>Delete</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            </>
          )}
        </Card>
      ) : null}

      {tab === "employees" ? (
        <Card
          title="Employees"
          action={<button className="btn small" type="button" onClick={() => setEditing(editing === "new" ? null : "new")}>Add employee</button>}
        >
          {editing === "new" ? (
            <EmployeeForm
              companies={data.companies}
              branches={data.branches}
              departments={data.departments}
              titles={data.job_titles}
              people={data.employees}
              token={token ?? ""}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => request(`${base}/employees`, { method: "POST", body: JSON.stringify(body) })}
            />
          ) : null}
          {data.employees.length === 0 ? <EmptyState title="No employees" note="Add a person record for this tenant." /> : (
            <>
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Name or employee number" />
            </div>
            {visibleEmployees.length === 0 ? (
              <EmptyState title="No matching employees" note={`Nothing matched “${listQuery.trim()}”.`} />
            ) : (
            <table>
              <thead><tr><th>Person</th><th>Number</th><th>Company</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visibleEmployees.map((row) => (
                  <tr key={row.id}>
                    <td colSpan={editing === row.id ? 5 : undefined} data-label={editing === row.id ? undefined : "Person"}>
                      {editing === row.id ? (
                        <EmployeeForm
                          initial={row}
                          companies={data.companies}
                          branches={data.branches}
                          departments={data.departments}
                          titles={data.job_titles}
                          people={data.employees}
                          token={token ?? ""}
                          kinPath={`${base}/employees/${row.id}/next-of-kin`}
                          supervisorsPath={`${base}/employees/${row.id}/supervisors`}
                          busy={busy}
                          onCancel={() => setEditing(null)}
                          onSubmit={(body) => request(`${base}/employees/${row.id}`, { method: "PATCH", body: JSON.stringify(body) })}
                        />
                      ) : (
                        <Link className="row-link" to={`/admin/tenants/${tenantId}/employees/${row.id}`}>
                          <PersonCell name={employeeName(row)} email={row.email ?? undefined} />
                        </Link>
                      )}
                    </td>
                    {editing === row.id ? null : (
                      <>
                        <td data-label="Number">{row.employee_number}</td>
                        <td data-label="Company">{companiesById.get(row.company_id)?.name ?? "—"}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td className="row-actions">
                          <Link className="btn ghost small" to={`/admin/tenants/${tenantId}/employees/${row.id}`}>View</Link>
                          <button className="btn ghost small" type="button" onClick={() => setEditing(row.id)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(`${base}/employees/${row.id}`, "employee")}>Delete</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            </>
          )}
        </Card>
      ) : null}

      {tab === "users" ? (
        <Card
          title="Users"
          action={<button className="btn small" type="button" onClick={() => setEditing(editing === "new" ? null : "new")}>Add user</button>}
        >
          {editing === "new" ? (
            <UserForm
              roles={roles}
              employees={data.employees}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => request(`${base}/users`, { method: "POST", body: JSON.stringify(body) })}
            />
          ) : null}
          {data.users.length === 0 ? <EmptyState title="No users" note="Add a login for this tenant." /> : (
            <>
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Name or email" />
            </div>
            {visibleUsers.length === 0 ? (
              <EmptyState title="No matching users" note={`Nothing matched “${listQuery.trim()}”.`} />
            ) : (
            <table>
              <thead><tr><th>Person</th><th>Role</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visibleUsers.map((row) => (
                  <tr key={row.id}>
                    <td colSpan={editing === row.id ? 4 : undefined} data-label={editing === row.id ? undefined : "Person"}>
                      {editing === row.id ? (
                        <UserForm
              roles={roles}
              employees={data.employees}
                          initial={row}
                          busy={busy}
                          onCancel={() => setEditing(null)}
                          onSubmit={(body) => request(`${base}/users/${row.id}`, { method: "PATCH", body: JSON.stringify(body) })}
                        />
                      ) : <PersonCell name={row.full_name} email={row.email} />}
                    </td>
                    {editing === row.id ? null : (
                      <>
                        <td data-label="Role">{roles.find(role => role.key === row.role)?.name || row.role}<small className="muted" style={{ display: "block" }}>{row.employee_id ? data.employees.find(employee => employee.id === row.employee_id) ? employeeName(data.employees.find(employee => employee.id === row.employee_id)!) : "Employee record linked" : "Employee portal not linked"}</small></td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => setEditing(row.id)}>Edit</button>
                          <button className="btn ghost small" type="button" disabled={busy} onClick={() => void remove(`${base}/users/${row.id}`, "user")}>Delete</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            </>
          )}
        </Card>
      ) : null}

      {tab === "documents" ? (
        <>
          <Card title="Document categories">
            <div className="filters" style={{ marginBottom: 12 }}>
              <label>
                Company
                <select value={docCompanyId} onChange={(event) => { setDocCompanyId(event.target.value); setDocCategory(""); }}>
                  {data.companies.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                </select>
              </label>
            </div>
            {token && docCompanyId ? (
              <DocumentCategories
                token={token}
                apiBase={base}
                companyId={docCompanyId}
                rows={(data.document_categories ?? []).filter((row) => row.company_id === docCompanyId)}
                canManage
                onChange={(rows) => setData({
                  ...data,
                  document_categories: [
                    ...(data.document_categories ?? []).filter((row) => row.company_id !== docCompanyId),
                    ...rows,
                  ],
                })}
              />
            ) : null}
          </Card>
          <Card title="Files">
            <div className="filters" style={{ marginBottom: 12 }}>
              <SearchField value={listQuery} onChange={setListQuery} placeholder="Name, number, or file" />
              <label>
                Category
                <select value={docCategory} onChange={(event) => setDocCategory(event.target.value)}>
                  <option value="">All categories</option>
                  {(data.document_categories ?? []).filter((row) => row.company_id === docCompanyId).map((row) => (
                    <option key={row.id} value={row.id}>{row.name}</option>
                  ))}
                </select>
              </label>
            </div>
            {docGroups.length === 0 ? (
              <EmptyState title="No documents" note="Uploads and lifecycle files for this company appear here." />
            ) : (
              docGroups.map((group) => (
                <div key={group.id || group.name} className="docs-group">
                  <div className="card-head docs-category" style={{ paddingLeft: 0, paddingRight: 0 }}>
                    <div>
                      <h3>{group.name} Documents</h3>
                      <p>{group.rows.length === 1 ? "1 file" : `${group.rows.length} files`}</p>
                    </div>
                  </div>
                  <table className="docs-table">
                    <colgroup>
                      <col className="docs-col-employee" />
                      <col />
                      <col className="docs-col-type" />
                      <col className="docs-col-size" />
                      <col className="docs-col-uploaded" />
                      <col className="docs-col-actions" />
                    </colgroup>
                    <thead><tr><th>Employee</th><th>File</th><th>Type</th><th>Size</th><th>Uploaded</th><th></th></tr></thead>
                    <tbody>
                      {group.rows.map((row) => (
                        <tr key={`${row.source}-${row.id}`}>
                          <td data-label="Employee">
                            <Link className="row-link" to={`/admin/tenants/${tenantId}/employees/${row.employee_id}`}>
                              {row.employee_name || "Employee"}
                            </Link>
                          </td>
                          <td className="docs-file" data-label="File">
                            <div>{row.filename}</div>
                            {row.source === "LIFECYCLE" && row.event_label ? (
                              <div className="muted">{row.event_label}</div>
                            ) : null}
                          </td>
                          <td data-label="Type">{documentFileType(row.filename, row.content_type)}</td>
                          <td data-label="Size">{formatFileSize(row.size)}</td>
                          <td data-label="Uploaded">{formatDate(row.created_at)}</td>
                          <td className="row-actions">
                            {token ? (
                              <>
                                <IconButton
                                  label="View"
                                  onClick={() => viewDocument(documentDownloadPath(base, row), token, row.filename, () => setViewingDoc(row))}
                                >
                                  <IconEye />
                                </IconButton>
                                <IconButton
                                  label="Download"
                                  onClick={() => void apiDownload(documentDownloadPath(base, row), token, row.filename)}
                                >
                                  <IconDownload />
                                </IconButton>
                              </>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))
            )}
          </Card>
        </>
      ) : null}
      {tab === "leave" ? (
        <>
          {data.companies.length === 0 ? (
            <section className="card"><p className="muted card-pad">Create a company first.</p></section>
          ) : token && opsCompany ? (
            <>
              <div className="filters">
                <label>
                  Company
                  <select value={opsCompany.id} onChange={(event) => setOpsCompanyId(event.target.value)}>
                    {data.companies.map((company) => (
                      <option key={company.id} value={company.id}>{company.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Branch
                  <select value={opsBranch?.id ?? ""} onChange={(event) => setOpsBranchId(event.target.value)}>
                    {opsBranches.map((row) => (
                      <option key={row.id} value={row.id}>{row.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="page-tabs">
                {(["Requests", "Balances", "Types", "Holidays"] as const).map((item) => (
                  <button key={item} type="button" className={leaveSection === item ? "active" : ""} onClick={() => setLeaveSection(item)}>
                    {item}
                  </button>
                ))}
              </div>
              {leaveSection === "Requests" ? (
                <section className="card">
                  <LeaveRequests
                    token={token}
                    apiBase={base}
                    companyId={opsCompany.id}
                    employees={opsEmployees}
                    types={opsTypes}
                    canManageHr
                    notify={setNotice}
                  />
                </section>
              ) : leaveSection === "Balances" ? (
                <section className="card">
                  <LeaveBalances
                    token={token}
                    apiBase={base}
                    companyId={opsCompany.id}
                    employees={opsEmployees}
                    types={opsTypes}
                    canManageHr
                  />
                </section>
              ) : leaveSection === "Types" ? (
                <section className="card">
                  <LeaveTypes
                    token={token}
                    apiBase={base}
                    companyId={opsCompany.id}
                    rows={opsTypes}
                    canManage
                    onChange={(rows) => setData({
                      ...data,
                      leave_types: [
                        ...(data.leave_types ?? []).filter((row) => row.company_id !== opsCompany.id),
                        ...rows,
                      ],
                    })}
                  />
                </section>
              ) : (
                <section className="card">
                  <PublicHolidays
                    token={token}
                    apiBase={base}
                    companyId={opsCompany.id}
                    branchId={opsBranch?.id}
                    countryId={opsBranch?.country_id}
                    rows={holidays}
                    canManage
                    onChange={setHolidays}
                  />
                </section>
              )}
            </>
          ) : null}
        </>
      ) : null}

      {tab === "attendance" ? (
        data.companies.length === 0 ? (
          <section className="card"><p className="muted card-pad">Create a company first.</p></section>
        ) : token ? (
          <>
            <div className="filters">
              <label>
                Company
                <select value={opsCompany?.id ?? ""} onChange={(event) => setOpsCompanyId(event.target.value)}>
                  {data.companies.map((company) => (
                    <option key={company.id} value={company.id}>{company.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Branch
                <select value={opsBranch?.id ?? ""} onChange={(event) => setOpsBranchId(event.target.value)}>
                  {opsBranches.map((row) => (
                    <option key={row.id} value={row.id}>{row.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <AttendanceRegister
              token={token}
              apiBase={base}
              company={opsCompany}
              branch={opsBranch}
              canManageHr
              canManageOrg
              employeeHref={(id) => `/admin/tenants/${tenantId}/employees/${id}`}
              addEmployeeHref={`/admin/tenants/${tenantId}?tab=employees`}
              hideHeader
            />
          </>
        ) : null
      ) : null}

      {tab === "payroll" ? (
        data.companies.length === 0 ? (
          <section className="card"><p className="muted card-pad">Create a company first.</p></section>
        ) : token ? (
          <>
            <div className="filters">
              <label>
                Company
                <select value={opsCompany?.id ?? ""} onChange={(event) => setOpsCompanyId(event.target.value)}>
                  {data.companies.map((company) => (
                    <option key={company.id} value={company.id}>{company.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Branch
                <select value={opsBranch?.id ?? ""} onChange={(event) => setOpsBranchId(event.target.value)}>
                  {opsBranches.map((row) => (
                    <option key={row.id} value={row.id}>{row.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="page-tabs">
              <button type="button" className={payrollSection === "runs" ? "active" : ""} onClick={() => setPayrollSection("runs")}>Runs</button>
              <button type="button" className={payrollSection === "settings" ? "active" : ""} onClick={() => setPayrollSection("settings")}>Configuration</button>
            </div>
            {payrollSection === "runs" ? (
              <PayrollBoard
                token={token}
                apiBase={base}
                company={opsCompany}
                branch={opsBranch}
                canManageHr
                employeeHref={(id) => `/admin/tenants/${tenantId}/employees/${id}`}
                hideHeader
              />
            ) : (
              <PayrollSettingsForm
                token={token}
                apiBase={base}
                company={opsCompany}
                branch={opsBranch}
                canManageHr
                notify={setNotice}
                hideHeader
              />
            )}
          </>
        ) : null
      ) : null}

      {tab === "lifecycle" ? (
        data.companies.length === 0 ? (
          <section className="card"><p className="muted card-pad">Create a company first.</p></section>
        ) : token ? (
          <LifecycleBoard
            token={token}
            apiBase={base}
            company={opsCompany}
            companies={data.companies}
            onCompanyId={setOpsCompanyId}
            departments={data.departments}
            titles={data.job_titles}
            employeeHref={(id) => `/admin/tenants/${tenantId}/employees/${id}`}
            hideHeader
          />
        ) : null
      ) : null}

      {["performance", "recruitment", "reports"].includes(tab) ? (
        token && tenantId && opsCompany ? <div className="stack"><Card title="Company" padded><label>Company<select value={opsCompany.id} onChange={event => setOpsCompanyId(event.target.value)}>{data.companies.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label></Card><Suspense fallback={<PageSkeleton />}>
          {tab === "reports" ? <AdminGeneralReports key={opsCompany.id} tenantId={tenantId} companyId={opsCompany.id} token={token} /> : <AdminModuleOversight key={`${tenantId}:${opsCompany.id}:${tab}`} tenantId={tenantId} companyId={opsCompany.id} token={token} module={tab as "performance" | "recruitment"} employeeNames={Object.fromEntries(data.employees.map(employee => [employee.id, employeeName(employee)]))} />}
        </Suspense></div> : <EmptyState title="No company available" note="Add a company to view its records." />
      ) : null}
      {tab === "access" && token && tenantId ? <Suspense fallback={<PageSkeleton />}><AdminRoles key={tenantId} user={{ id: adminSession.get()?.id || "", role: "OWNER" }} canManage notify={message => { setNotice(message); void load().catch((err: Error) => setError(err.message)); }} apiBase={`/platform/tenants/${tenantId}/modules/access`} token={token} /></Suspense> : null}
      {tab === "more" ? <Card title="External connections" padded><p className="muted">External payroll, identity and messaging connections have not been configured for this system.</p><p>Google sign-in requires a Google OAuth client ID in the server settings. Employees can link Google from their account page once it is configured.</p></Card> : null}

      {viewingDoc && token ? (
        <DocumentPreview
          path={documentDownloadPath(base, viewingDoc)}
          filename={viewingDoc.filename}
          contentType={viewingDoc.content_type}
          token={token}
          onClose={() => setViewingDoc(null)}
        />
      ) : null}
    </>
  );
}

function FormActions({ busy, onCancel }: { busy: boolean; onCancel: () => void }) {
  return (
    <div className="actions">
      <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      <button className="btn ghost small" type="button" onClick={onCancel}>Cancel</button>
    </div>
  );
}

function CompanyForm({
  initial,
  busy,
  onCancel,
  onSubmit,
}: {
  initial?: Company;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Record<string, string | null>) => void;
}) {
  const [form, setForm] = useState({
    name: initial?.name ?? "",
    legal_name: initial?.legal_name ?? "",
    email: initial?.email ?? "",
    phone: initial?.phone ?? "",
    website: initial?.website ?? "",
    status: initial?.status ?? "ACTIVE",
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({
      name: form.name.trim(),
      legal_name: emptyToNull(form.legal_name),
      email: emptyToNull(form.email),
      phone: emptyToNull(form.phone),
      website: emptyToNull(form.website),
      status: form.status,
    });
  }
  return (
    <form className="nested-block" onSubmit={submit}>
      <div className="form-grid">
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Legal name<input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></label>
        <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Phone<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
        <label>Website<input value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} /></label>
        <label>Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      <FormActions busy={busy} onCancel={onCancel} />
    </form>
  );
}

function BranchForm({
  initial,
  companies,
  countries,
  busy,
  onCancel,
  onSubmit,
}: {
  initial?: Branch;
  companies: Company[];
  countries: Country[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Record<string, string | null>) => void;
}) {
  const [form, setForm] = useState({
    company_id: initial?.company_id ?? companies[0]?.id ?? "",
    country_id: initial?.country_id ?? countries[0]?.id ?? "",
    name: initial?.name ?? "",
    code: initial?.code ?? "",
    city: initial?.city ?? "",
    status: initial?.status ?? "ACTIVE",
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, string | null> = {
      country_id: form.country_id,
      name: form.name.trim(),
      code: form.code.trim(),
      city: emptyToNull(form.city),
      status: form.status,
    };
    if (!initial) body.company_id = form.company_id;
    onSubmit(body);
  }
  return (
    <form className="nested-block" onSubmit={submit}>
      <div className="form-grid">
        {initial ? null : (
          <label>Company
            <select required value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
              {companies.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        )}
        <label>Country
          <select required value={form.country_id} onChange={(e) => setForm({ ...form, country_id: e.target.value })}>
            {countries.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
        </label>
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Code<input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
        <label>City<input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
        <label>Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      <FormActions busy={busy} onCancel={onCancel} />
    </form>
  );
}

function NamedOrgForm({
  initial,
  companies,
  hideCompany,
  busy,
  onCancel,
  onSubmit,
}: {
  initial?: Department;
  companies: Company[];
  hideCompany?: boolean;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Record<string, string | null>) => void;
}) {
  const [form, setForm] = useState({
    company_id: initial?.company_id ?? companies[0]?.id ?? "",
    name: initial?.name ?? "",
    code: initial?.code ?? "",
    description: initial?.description ?? "",
    status: initial?.status ?? "ACTIVE",
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, string | null> = {
      name: form.name.trim(),
      code: emptyToNull(form.code),
      description: emptyToNull(form.description),
      status: form.status,
    };
    if (!hideCompany) body.company_id = form.company_id;
    onSubmit(body);
  }
  return (
    <form className="nested-block" onSubmit={submit}>
      <div className="form-grid">
        {hideCompany ? null : (
          <label>Company
            <select required value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
              {companies.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        )}
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Code<input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
        <label>Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label style={{ gridColumn: "1 / -1" }}>Description<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
      </div>
      <FormActions busy={busy} onCancel={onCancel} />
    </form>
  );
}

function JobTitleForm({
  initial,
  companies,
  departments,
  busy,
  onCancel,
  onSubmit,
}: {
  initial?: JobTitle;
  companies: Company[];
  departments: Department[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Record<string, string | null>) => void;
}) {
  const [form, setForm] = useState({
    company_id: initial?.company_id ?? companies[0]?.id ?? "",
    department_id: initial?.department_id ?? "",
    name: initial?.name ?? "",
    code: initial?.code ?? "",
    status: initial?.status ?? "ACTIVE",
  });
  const companyDepartments = departments.filter((row) => row.company_id === form.company_id);
  function submit(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, string | null> = {
      department_id: emptyToNull(form.department_id),
      name: form.name.trim(),
      code: emptyToNull(form.code),
      status: form.status,
    };
    if (!initial) body.company_id = form.company_id;
    onSubmit(body);
  }
  return (
    <form className="nested-block" onSubmit={submit}>
      <div className="form-grid">
        {initial ? null : (
          <label>Company
            <select required value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value, department_id: "" })}>
              {companies.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        )}
        <label>Department
          <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
            <option value="">None</option>
            {companyDepartments.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
        </label>
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Code<input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
        <label>Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      <FormActions busy={busy} onCancel={onCancel} />
    </form>
  );
}

function EmployeeForm({
  initial,
  companies,
  branches,
  departments,
  titles,
  people,
  token,
  kinPath,
  supervisorsPath,
  busy,
  onCancel,
  onSubmit,
}: {
  initial?: Employee;
  companies: Company[];
  branches: Branch[];
  departments: Department[];
  titles: JobTitle[];
  people: Employee[];
  token: string;
  kinPath?: string;
  supervisorsPath?: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    company_id: initial?.company_id ?? companies[0]?.id ?? "",
    branch_id: initial?.branch_id ?? "",
    department_id: initial?.department_id ?? "",
    job_title_id: initial?.job_title_id ?? "",
    first_name: initial?.first_name ?? "",
    other_names: initial?.other_names ?? "",
    last_name: initial?.last_name ?? "",
    date_of_birth: initial?.date_of_birth ?? "",
    id_number: initial?.id_number ?? "",
    nssf_no: initial?.nssf_no ?? "",
    shif_no: initial?.shif_no ?? "",
    email: initial?.email ?? "",
    personal_email: initial?.personal_email ?? "",
    phone: initial?.phone ?? "",
    other_phone: initial?.other_phone ?? "",
    employment_type: initial?.employment_type ?? "FULL_TIME",
    date_joined: initial?.date_joined ?? "",
    date_ended: initial?.date_ended ?? "",
  });
  const [kin, setKin] = useState<NextOfKinDraft[]>([]);
  const [kinError, setKinError] = useState<string | null>(null);
  const [supervisorIds, setSupervisorIds] = useState<string[]>([]);
  useEffect(() => {
    if (!kinPath || !token) return;
    api<NextOfKin[]>(kinPath, { token })
      .then((rows) => setKin(rows.map(nextOfKinFromRow)))
      .catch(() => undefined);
  }, [kinPath, token]);
  useEffect(() => {
    if (!supervisorsPath || !token) return;
    api<Supervisor[]>(supervisorsPath, { token })
      .then((rows) => setSupervisorIds(rows.map((row) => row.id)))
      .catch(() => undefined);
  }, [supervisorsPath, token]);
  const companyId = initial?.company_id ?? form.company_id;
  const companyBranches = branches.filter((row) => row.company_id === companyId);
  const companyDepartments = departments.filter((row) => row.company_id === companyId);
  const companyTitles = titles.filter((row) => row.company_id === companyId);
  function submit(event: FormEvent) {
    event.preventDefault();
    const problem = nextOfKinError(kin);
    if (problem) {
      setKinError(problem);
      return;
    }
    setKinError(null);
    const body: Record<string, unknown> = {
      branch_id: form.branch_id,
      department_id: emptyToNull(form.department_id),
      job_title_id: emptyToNull(form.job_title_id),
      first_name: form.first_name.trim(),
      other_names: emptyToNull(form.other_names),
      last_name: form.last_name.trim(),
      date_of_birth: emptyToNull(form.date_of_birth),
      id_number: emptyToNull(form.id_number),
      nssf_no: emptyToNull(form.nssf_no),
      shif_no: emptyToNull(form.shif_no),
      email: emptyToNull(form.email),
      personal_email: emptyToNull(form.personal_email),
      phone: emptyToNull(form.phone),
      other_phone: emptyToNull(form.other_phone),
      employment_type: form.employment_type,
      date_joined: emptyToNull(form.date_joined),
      date_ended: form.employment_type === "INTERN" || form.employment_type === "PROBATION" || form.employment_type === "CONTRACT"
        ? emptyToNull(form.date_ended)
        : null,
      next_of_kin: nextOfKinPayload(kin),
      supervisor_ids: supervisorIds.filter(Boolean),
    };
    if (!initial) body.company_id = form.company_id;
    onSubmit(body);
  }
  return (
    <form className="nested-block" onSubmit={submit}>
      <div className="form-grid">
        {initial ? null : (
          <label>Company
            <select required value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value, branch_id: "", department_id: "", job_title_id: "" })}>
              {companies.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        )}
        <label>Branch
          <select required value={form.branch_id} onChange={(e) => setForm({ ...form, branch_id: e.target.value })}>
            <option value="">Select</option>
            {companyBranches.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
        </label>
        <label>First name<input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></label>
        <label>Other names<input value={form.other_names} onChange={(e) => setForm({ ...form, other_names: e.target.value })} /></label>
        <label>Last name<input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} /></label>
        <label>Date of birth<input type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} /></label>
        <label>ID no.<input value={form.id_number} onChange={(e) => setForm({ ...form, id_number: e.target.value })} autoComplete="off" /></label>
        <label>NSSF no.<input value={form.nssf_no} onChange={(e) => setForm({ ...form, nssf_no: e.target.value })} autoComplete="off" /></label>
        <label>SHIF no.<input value={form.shif_no} onChange={(e) => setForm({ ...form, shif_no: e.target.value })} autoComplete="off" /></label>
        <label>Work email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Personal email<input type="email" value={form.personal_email} onChange={(e) => setForm({ ...form, personal_email: e.target.value })} /></label>
        <label>Phone<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
        <label>Second phone<input value={form.other_phone} onChange={(e) => setForm({ ...form, other_phone: e.target.value })} /></label>
        <label>Department
          <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
            <option value="">None</option>
            {companyDepartments.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
        </label>
        <label>Job title
          <select value={form.job_title_id} onChange={(e) => setForm({ ...form, job_title_id: e.target.value })}>
            <option value="">None</option>
            {companyTitles.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
        </label>
        <label>Employment
          <select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}>
            {EMPLOYMENT.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>Start date<input type="date" value={form.date_joined} onChange={(e) => setForm({ ...form, date_joined: e.target.value })} /></label>
        {form.employment_type === "INTERN" || form.employment_type === "PROBATION" || form.employment_type === "CONTRACT" ? (
          <label>End date
            <input
              type="date"
              required={form.employment_type !== "CONTRACT"}
              value={form.date_ended}
              onChange={(e) => setForm({ ...form, date_ended: e.target.value })}
            />
          </label>
        ) : null}
      </div>
      <SupervisorFields
        people={people.filter((row) => row.company_id === companyId)}
        excludeId={initial?.id}
        selectedIds={supervisorIds}
        onChange={setSupervisorIds}
      />
      <NextOfKinFields rows={kin} onChange={(rows) => { setKin(rows); setKinError(null); }} />
      {kinError ? <p className="error">{kinError}</p> : null}
      <FormActions busy={busy} onCancel={onCancel} />
    </form>
  );
}

function UserForm({
  roles, employees,
  initial,
  busy,
  onCancel,
  onSubmit,
}: {
  roles: AccessRole[];
  employees: Employee[];
  initial?: User;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Record<string, string | null>) => void;
}) {
  const [form, setForm] = useState({
    employee_id: initial?.employee_id ?? "",
    full_name: initial?.full_name ?? "",
    email: initial?.email ?? "",
    password: "",
    role: initial?.role ?? "EMPLOYEE",
    status: initial?.status ?? "ACTIVE",
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, string | null> = {
      employee_id: form.employee_id || null,
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      role: form.role,
      status: form.status,
    };
    if (form.password) body.password = form.password;
    onSubmit(body);
  }
  return (
    <form className="nested-block" onSubmit={submit}>
      <div className="form-grid">
        <label>Name<input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
        <label>Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password
          <input
            type="password"
            minLength={initial ? undefined : 8}
            required={!initial}
            placeholder={initial ? "Leave blank to keep" : ""}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </label>
        <label>Employee portal record<select value={form.employee_id} onChange={e => setForm({ ...form, employee_id: e.target.value })}><option value="">No employee record linked</option>{employees.map(employee => <option key={employee.id} value={employee.id}>{employeeName(employee)} ({employee.employee_number})</option>)}</select><small className="muted">Link a record to enable personal attendance, leave, payslips and reviews.</small></label>
        <label>Role
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {roles.map(role => <option key={role.key} value={role.key}>{role.name}</option>)}
          </select>
        </label>
        <label>Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      <FormActions busy={busy} onCancel={onCancel} />
    </form>
  );
}

