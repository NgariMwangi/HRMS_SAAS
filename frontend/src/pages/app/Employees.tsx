import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { IconPlus } from "../../components/icons";
import { employeeName, type Department, type Employee, type JobTitle } from "../../types";
import { EmptyState, matchesSearch, PageHeader, PersonCell, SearchField, StatusPill, TableSkeleton } from "../../ui";

function typeLabel(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

export default function EmployeesPage() {
  const { token, company, branch, companies, branches, setCompanyId, setBranchId, hasPermission } = useWorkspace();
  const canManageOrg = hasPermission("people.manage");
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [rows, setRows] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [branchFilter, setBranchFilter] = useState(branch?.id ?? "");
  const [statusFilter, setStatusFilter] = useState("current");

  useEffect(() => {
    setBranchFilter(branch?.id ?? "");
  }, [branch?.id]);

  useEffect(() => {
    if (!company) {
      setRows([]);
      setDepartments([]);
      setTitles([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const search = new URLSearchParams({ company_id: company.id });
    if (branchFilter) search.set("branch_id", branchFilter);
    if (statusFilter === "terminated") search.set("status", "TERMINATED");
    if (statusFilter === "all") search.set("status", "all");
    Promise.all([
      api<Employee[]>(`/employees?${search.toString()}`, { token }),
      api<Department[]>(`/departments?company_id=${company.id}`, { token }),
      api<JobTitle[]>(`/job-titles?company_id=${company.id}`, { token }),
    ])
      .then(([people, deptRows, titleRows]) => {
        setRows(people);
        setDepartments(deptRows);
        setTitles(titleRows);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [token, company?.id, branchFilter, statusFilter]);

  useEffect(() => {
    setQuery(params.get("q") ?? "");
  }, [params]);

  function changeQuery(value: string) {
    setQuery(value);
    const next = new URLSearchParams(params);
    if (value.trim()) next.set("q", value);
    else next.delete("q");
    setParams(next, { replace: true });
  }

  const departmentById = useMemo(() => new Map(departments.map((row) => [row.id, row])), [departments]);
  const titleById = useMemo(() => new Map(titles.map((row) => [row.id, row])), [titles]);
  const branchById = useMemo(() => new Map(branches.map((row) => [row.id, row])), [branches]);
  const visible = useMemo(
    () => rows.filter((row) => matchesSearch(query, employeeName(row), row.employee_number, row.email, row.personal_email)),
    [rows, query],
  );

  return (
    <div className="titles-page">
      <PageHeader
        title="Employees"
        description={`${company?.name ?? "This company"}${branchFilter ? ` · ${branchById.get(branchFilter)?.name ?? "Branch"}` : " · all branches"}. People in this directory belong to this company only.`}
        actions={
          canManageOrg ? (
            <Link className="btn small" to="/app/people/new"><IconPlus /> Add employee</Link>
          ) : null
        }
      />
      <div className="filters">
        <SearchField value={query} onChange={changeQuery} placeholder="Name or employee number" />
        <label>
          Company
          <select value={company?.id ?? ""} onChange={(event) => setCompanyId(event.target.value)}>
            {companies.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
        <label>
          Branch
          <select value={branchFilter} onChange={(event) => {
            setBranchFilter(event.target.value);
            if (event.target.value) setBranchId(event.target.value);
          }}>
            <option value="">All branches</option>
            {branches.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="current">Current</option>
            <option value="terminated">Terminated</option>
            <option value="all">All</option>
          </select>
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <section className="card">
        {loading ? (
          <TableSkeleton />
        ) : visible.length === 0 ? (
          <EmptyState
            title={query.trim() ? "No matching employees" : "No employees in this company yet"}
            note={query.trim() ? `Nothing matched “${query.trim()}”.` : "Add people after departments and job titles are set up."}
            action={canManageOrg ? <Link className="btn small" to="/app/people/new">Add employee</Link> : null}
          />
        ) : (
          <>
          <table className="org-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Title</th>
                <th>Department</th>
                <th>Branch</th>
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id} className="is-clickable">
                  <td data-label="Employee">
                    <Link to={`/app/people/${row.id}`} className="row-link">
                      <PersonCell
                        name={employeeName(row)}
                        email={row.email ?? row.employee_number}
                      />
                    </Link>
                  </td>
                  <td data-label="Title">{row.job_title_id ? titleById.get(row.job_title_id)?.name ?? "—" : "—"}</td>
                  <td data-label="Department">{row.department_id ? departmentById.get(row.department_id)?.name ?? "—" : "—"}</td>
                  <td data-label="Branch">{branchById.get(row.branch_id)?.name ?? "—"}</td>
                  <td data-label="Type"><StatusPill value={typeLabel(row.employment_type)} /></td>
                  <td data-label="Status"><StatusPill value={row.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="titles-list">
            {visible.map((row) => (
              <li key={row.id} className="titles-row">
                <Link to={`/app/people/${row.id}`} className="titles-row-top row-link">
                  <PersonCell
                    name={employeeName(row)}
                    email={[
                      row.job_title_id ? titleById.get(row.job_title_id)?.name : null,
                      row.department_id ? departmentById.get(row.department_id)?.name : null,
                      branchById.get(row.branch_id)?.name,
                    ].filter(Boolean).join(" · ") || row.email || row.employee_number}
                  />
                  <StatusPill value={row.status} />
                </Link>
              </li>
            ))}
          </ul>
          </>
        )}
      </section>
    </div>
  );
}
