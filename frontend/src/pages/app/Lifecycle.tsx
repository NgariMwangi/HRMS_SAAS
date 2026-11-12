import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api, apiUrl } from "../../api";
import { EventDocuments, extensionDetail } from "../../components/LifecyclePanel";
import { suspensionPayText, type Department, type JobTitle, type LifecycleEvent } from "../../types";
import { EmptyState, matchesSearch, PageHeader, SearchField, StatusPill, TableSkeleton, formatDate } from "../../ui";

function eventLabel(row: LifecycleEvent): string {
  if (row.event_type === "TRANSFERRED") return row.reason === "IN" ? "Transferred into company" : "Transferred to another company";
  if (row.event_type === "HIRED") return "Employed";
  if (row.event_type === "SUSPENDED") return "Suspended";
  if (row.event_type === "REINSTATED") return "Unsuspended";
  if (row.event_type === "TERMINATED") return "Terminated";
  if (row.event_type === "EXTENDED") {
    if (row.employment_type === "INTERN") return "Internship extended";
    if (row.employment_type === "CONTRACT") return "Contract extended";
    return "Extended";
  }
  if (row.event_type === "REHIRED") return row.reason === "NEW_RECORD" ? "Rehired as new record" : "Rehired";
  if (row.reason === "PROMOTION") return "Promoted";
  if (row.reason === "DEMOTION") return "Demoted";
  if (row.reason === "DEPARTMENT_CHANGE") return "Department changed";
  if (row.reason === "TITLE_CHANGE") return "Job title changed";
  return "Role changed";
}

function eventDetail(
  row: LifecycleEvent,
  dept: Map<string, string>,
  title: Map<string, string>,
): string {
  const parts: string[] = [];
  if (row.to_job_title_id && row.to_job_title_id !== row.from_job_title_id) {
    const next = title.get(row.to_job_title_id);
    if (next) parts.push(next);
  }
  if (row.to_department_id && row.to_department_id !== row.from_department_id) {
    const next = dept.get(row.to_department_id);
    if (next) parts.push(next);
  }
  if (row.event_type === "EXTENDED") {
    const extra = extensionDetail(row);
    if (extra) parts.push(extra);
  }
  if (row.event_type === "SUSPENDED" && suspensionPayText(row)) parts.push(suspensionPayText(row) ?? "");
  if (row.note) parts.push(row.note);
  if (parts.length === 0 && row.event_type !== "EXTENDED") parts.push(row.reason ?? "—");
  return parts.filter(Boolean).join(" · ");
}

export type LifecycleScope = {
  token: string;
  apiBase?: string;
  company: { id: string; name: string } | null;
  companies: { id: string; name: string }[];
  onCompanyId?: (id: string) => void;
  departments?: Department[];
  titles?: JobTitle[];
  employeeHref: (id: string) => string;
  hideHeader?: boolean;
};

export function LifecycleBoard({
  token,
  apiBase = "",
  company,
  companies,
  onCompanyId,
  departments: departmentsProp,
  titles: titlesProp,
  employeeHref,
  hideHeader,
}: LifecycleScope) {
  const [rows, setRows] = useState<LifecycleEvent[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [eventType, setEventType] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const search = new URLSearchParams({ company_id: company.id });
    if (eventType) search.set("event_type", eventType);
    const loadEvents = api<LifecycleEvent[]>(apiUrl(apiBase, `/lifecycle?${search.toString()}`), { token });
    const loadDept = departmentsProp
      ? Promise.resolve(departmentsProp.filter((row) => row.company_id === company.id))
      : api<Department[]>(apiUrl(apiBase, `/departments?company_id=${company.id}`), { token });
    const loadTitles = titlesProp
      ? Promise.resolve(titlesProp.filter((row) => row.company_id === company.id))
      : api<JobTitle[]>(apiUrl(apiBase, `/job-titles?company_id=${company.id}`), { token });
    Promise.all([loadEvents, loadDept, loadTitles])
      .then(([events, deptRows, titleRows]) => {
        setRows(events);
        setDepartments(deptRows);
        setTitles(titleRows);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [token, company?.id, eventType, apiBase, departmentsProp, titlesProp]);

  useEffect(() => {
    setQuery("");
  }, [company?.id]);

  const dept = useMemo(() => new Map(departments.map((row) => [row.id, row.name])), [departments]);
  const title = useMemo(() => new Map(titles.map((row) => [row.id, row.name])), [titles]);
  const visible = useMemo(
    () => rows.filter((row) => matchesSearch(query, row.employee_name, row.employee_number)),
    [rows, query],
  );

  return (
    <div className="titles-page">
      {hideHeader ? null : (
      <PageHeader
        title="Employee lifecycle"
        description={`Joiners, leavers, suspensions, and role changes for ${company?.name ?? "this company"}.`}
      />
      )}
      <div className="filters">
        <SearchField value={query} onChange={setQuery} placeholder="Name or employee number" />
        <label>
          Company
          <select value={company?.id ?? ""} onChange={(event) => onCompanyId?.(event.target.value)} disabled={!onCompanyId}>
            {companies.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
        <label>
          Event
          <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
            <option value="">All events</option>
            <option value="HIRED">Employed</option>
            <option value="SUSPENDED">Suspended</option>
            <option value="REINSTATED">Unsuspended</option>
            <option value="ROLE_CHANGED">Role change</option>
            <option value="TERMINATED">Terminated</option>
            <option value="EXTENDED">Extended</option>
            <option value="REHIRED">Rehired</option>
          </select>
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <section className="card">
        {loading ? (
          <TableSkeleton cols={4} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={query.trim() ? "No matching lifecycle events" : "No lifecycle events"}
            note={query.trim() ? `Nothing matched “${query.trim()}”.` : "Adding or changing an employee writes the first events here."}
          />
        ) : (
          <>
          <table className="org-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Event</th>
                <th>Effective</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id}>
                  <td data-label="Employee">
                    <Link className="row-link" to={employeeHref(row.employee_id)}>
                      {row.employee_name ?? "Employee"}
                    </Link>
                    <div className="muted">{row.employee_number}</div>
                  </td>
                  <td data-label="Event"><StatusPill value={eventLabel(row)} /></td>
                  <td data-label="Effective">{formatDate(row.effective_on)}</td>
                  <td data-label="Detail">
                    {row.to_job_title_id && row.to_job_title_id !== row.from_job_title_id
                      ? title.get(row.to_job_title_id) ?? ""
                      : null}
                    {row.to_department_id && row.to_department_id !== row.from_department_id
                      ? `${row.to_job_title_id ? " · " : ""}${dept.get(row.to_department_id) ?? ""}`
                      : null}
                    {row.event_type === "EXTENDED" ? extensionDetail(row) : null}
                    {row.event_type === "SUSPENDED" && suspensionPayText(row)
                      ? `${suspensionPayText(row)}${row.note || row.reason ? " · " : ""}`
                      : null}
                    {row.note ? `${row.to_job_title_id || row.to_department_id ? " · " : ""}${row.note}` : null}
                    {!row.note && !row.to_job_title_id && !row.to_department_id && row.event_type !== "EXTENDED" ? (row.reason ?? "—") : null}
                    <EventDocuments event={row} token={token} apiBase={apiBase} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="titles-list">
            {visible.map((row) => (
              <li key={row.id} className="titles-row">
                <div className="titles-row-top">
                  <div className="titles-main">
                    <strong>
                      <Link className="row-link" to={employeeHref(row.employee_id)}>
                        {row.employee_name ?? "Employee"}
                      </Link>
                    </strong>
                    <span>{[row.employee_number, formatDate(row.effective_on), eventDetail(row, dept, title)].filter(Boolean).join(" · ")}</span>
                  </div>
                  <StatusPill value={eventLabel(row)} />
                </div>
                <EventDocuments event={row} token={token} apiBase={apiBase} />
              </li>
            ))}
          </ul>
          </>
        )}
      </section>
    </div>
  );
}

export default function LifecyclePage() {
  const { token, company, companies, setCompanyId } = useWorkspace();
  return (
    <LifecycleBoard
      token={token}
      company={company}
      companies={companies}
      onCompanyId={setCompanyId}
      employeeHref={(id) => `/app/people/${id}`}
    />
  );
}

