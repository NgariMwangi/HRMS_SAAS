import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AuditLog } from "../types";
import { EmptyState, SearchField, StatusPill, TableSkeleton, formatDateTime, matchesSearch } from "../ui";

function outcomeLabel(value: string): string {
  return value === "SUCCESS" ? "Successful" : "Failed";
}

const RESOURCE_LABELS: Record<string, { one: string; many: string }> = {
  me: { one: "profile", many: "profile" },
  login: { one: "sign-in", many: "sign-in" },
  register: { one: "account", many: "account" },
  refresh: { one: "session", many: "session" },
  companies: { one: "company", many: "companies" },
  branches: { one: "branch", many: "branches" },
  departments: { one: "department", many: "departments" },
  "job-titles": { one: "job title", many: "job titles" },
  employees: { one: "employee", many: "employees" },
  documents: { one: "document", many: "documents" },
  "document-categories": { one: "document category", many: "document categories" },
  lifecycle: { one: "lifecycle event", many: "lifecycle events" },
  "leave-types": { one: "leave type", many: "leave types" },
  "leave-requests": { one: "leave request", many: "leave requests" },
  "leave-balances": { one: "leave balance", many: "leave balances" },
  "public-holidays": { one: "public holiday", many: "public holidays" },
  "audit-logs": { one: "audit log", many: "audit logs" },
  countries: { one: "country", many: "countries" },
  tenants: { one: "tenant", many: "tenants" },
  attendance: { one: "attendance", many: "attendance" },
  payroll: { one: "payroll", many: "payroll" },
  compensation: { one: "salary", many: "salaries" },
  "payroll-packs": { one: "payroll pack", many: "payroll packs" },
};

const UUID_SEGMENT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function resourceName(path: string, plural: boolean): string {
  const parts = path.split("/").filter((part) => part && part !== "auth" && part !== "platform");
  const key = parts[0] ?? "";
  const labels = RESOURCE_LABELS[key];
  if (labels) return plural ? labels.many : labels.one;
  return key.replace(/-/g, " ") || "resource";
}

function describeAction(row: AuditLog): string {
  const method = row.method.toUpperCase();
  const parts = row.path.split("/").filter((part) => part && part !== "auth" && part !== "platform");
  const hasId = parts.some((part) => UUID_SEGMENT.test(part));
  const name = resourceName(row.path, method === "GET" && !hasId);
  if (method === "POST") return `Created ${name}`;
  if (method === "PATCH" || method === "PUT") return `Updated ${name}`;
  if (method === "DELETE") return `Deleted ${name}`;
  if (method === "GET") return `Viewed ${name}`;
  return row.action;
}

export function AuditLogs({
  token,
  path,
  timeZone,
}: {
  token: string;
  path: string;
  timeZone?: string | null;
}) {
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [query, setQuery] = useState("");
  const [outcome, setOutcome] = useState("");
  const [kind, setKind] = useState<"changes" | "all">("changes");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (outcome) params.set("outcome", outcome);
    const suffix = params.toString() ? `?${params}` : "";
    setLoading(true);
    api<AuditLog[]>(`${path}${suffix}`, { token })
      .then((list) => {
        setRows(list);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [path, outcome, token]);

  const visible = useMemo(
    () =>
      rows.filter((row) => {
        if (kind === "changes" && row.method === "GET") return false;
        return matchesSearch(
          query,
          row.requester,
          row.action,
          describeAction(row),
          row.request,
          row.response,
          row.outcome,
        );
      }),
    [rows, query, kind],
  );

  return (
    <>
      <div className="card-pad" style={{ paddingBottom: 0 }}>
        <div className="filters">
          <SearchField value={query} onChange={setQuery} placeholder="Requester, action, or response" />
          <label>
            Show
            <select value={kind} onChange={(event) => setKind(event.target.value as "changes" | "all")}>
              <option value="changes">Changes</option>
              <option value="all">All requests</option>
            </select>
          </label>
          <label>
            Result
            <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="">All</option>
              <option value="SUCCESS">Successful</option>
              <option value="FAILED">Failed</option>
            </select>
          </label>
        </div>
        {error ? <p className="error">{error}</p> : null}
      </div>
      {loading ? (
        <TableSkeleton rows={6} cols={4} />
      ) : visible.length === 0 ? (
        <EmptyState
          title={query.trim() || outcome || kind === "changes" ? "No matching entries" : "No requests recorded yet"}
          note={
            kind === "changes" && !query.trim() && !outcome
              ? "Creates, edits, and deletes will appear here. Switch to All requests to include page loads."
              : query.trim() || outcome
                ? "Nothing matched those filters."
                : "Workspace requests will appear here."
          }
        />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Requester</th>
              <th>Action / request</th>
              <th>Response</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id}>
                <td data-label="Requester">{row.requester}</td>
                <td data-label="Action / request">
                  <strong>{describeAction(row)}</strong>
                  {row.request ? <div className="muted">{row.request}</div> : null}
                </td>
                <td data-label="Response">
                  <StatusPill value={outcomeLabel(row.outcome)} />
                  <div className="muted">{row.response}{row.status_code ? ` · ${row.status_code}` : ""}</div>
                </td>
                <td data-label="When">{formatDateTime(row.created_at, timeZone)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
