import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import MyAttendance from "../../components/MyAttendance";
import { api, apiUrl } from "../../api";
import type { AttendanceRow } from "../../types";
import { EmptyState, Kpi, KpiRowSkeleton, PageHeader, PersonCell, StatusPill, TableSkeleton, formatDateTime } from "../../ui";

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function statusLabel(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

export type AttendanceScope = {
  token: string;
  apiBase?: string;
  company: { id: string; name: string } | null;
  branch: { id: string; name: string; timezone?: string | null } | null;
  canManageHr: boolean;
  canManageOrg?: boolean;
  employeeHref: (id: string) => string;
  addEmployeeHref?: string | null;
  hideHeader?: boolean;
};

export function AttendanceRegister({
  token,
  apiBase = "",
  company,
  branch,
  canManageHr,
  canManageOrg,
  employeeHref,
  addEmployeeHref,
  hideHeader,
}: AttendanceScope) {
  const [workOn, setWorkOn] = useState(todayIso);
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    if (!company || !branch) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const list = await api<AttendanceRow[]>(
        apiUrl(apiBase, `/attendance?company_id=${company.id}&branch_id=${branch.id}&work_on=${workOn}`),
        { token },
      );
      setRows(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load attendance");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [company?.id, branch?.id, workOn, token, apiBase]);

  const counts = useMemo(() => {
    const tally = { present: 0, absent: 0, late: 0, leave: 0 };
    for (const row of rows) {
      if (row.status === "PRESENT") tally.present += 1;
      if (row.status === "ABSENT") tally.absent += 1;
      if (row.status === "LATE") tally.late += 1;
      if (row.status === "ON_LEAVE") tally.leave += 1;
    }
    return tally;
  }, [rows]);

  async function mark(row: AttendanceRow, status: "PRESENT" | "LATE" | "ABSENT") {
    if (!canManageHr || row.on_leave) return;
    setBusyId(row.employee_id);
    try {
      const saved = await api<AttendanceRow>(apiUrl(apiBase, "/attendance"), {
        method: "PUT",
        token,
        body: JSON.stringify({ employee_id: row.employee_id, work_on: workOn, status }),
      });
      setRows((current) => current.map((item) => (item.employee_id === saved.employee_id ? saved : item)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusyId(null);
    }
  }

  async function unlockDevice(row: AttendanceRow) {
    if (!canManageHr) return;
    setBusyId(row.employee_id);
    try {
      await api(apiUrl(apiBase, `/employees/${row.employee_id}/clock-device/reset`), { method: "POST", token });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unlock device");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="titles-page">
      {hideHeader ? null : (
        <PageHeader
          title="Attendance"
          description={`${company?.name ?? "This company"}${branch ? ` · ${branch.name}` : ""}. People clock in from the employee app. You can correct the register here.`}
        />
      )}
      <div className="filters">
        <label>
          Date
          <input type="date" value={workOn} onChange={(event) => setWorkOn(event.target.value)} />
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {!company || !branch ? (
        <section className="card">
          <EmptyState title="Select a branch" note="Attendance is listed for the selected company and branch." />
        </section>
      ) : loading ? (
        <>
          <KpiRowSkeleton />
          <section className="card"><TableSkeleton cols={6} /></section>
        </>
      ) : (
        <>
          <div className="kpis">
            <Kpi label="Present" value={counts.present} />
            <Kpi label="Absent" value={counts.absent} />
            <Kpi label="Late" value={counts.late} />
            <Kpi label="On leave" value={counts.leave} />
          </div>
          <section className="card">
            {rows.length === 0 ? (
              <EmptyState
                title="No one on this register"
                note="Active employees at this branch will appear here. Terminated records stay off the list."
                action={canManageOrg && addEmployeeHref ? <Link className="btn small" to={addEmployeeHref}>Add employee</Link> : null}
              />
            ) : (
              <>
                <table className="org-table">
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Status</th>
                      <th>In</th>
                      <th>Out</th>
                      <th>Login / device</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.employee_id}>
                        <td data-label="Employee">
                          <Link to={employeeHref(row.employee_id)} className="row-link">
                            <PersonCell name={row.employee_name} email={row.employee_number} />
                          </Link>
                        </td>
                        <td data-label="Status"><StatusPill value={statusLabel(row.status)} /></td>
                        <td data-label="In">{formatDateTime(row.checked_in_at, branch.timezone)}</td>
                        <td data-label="Out">{formatDateTime(row.checked_out_at, branch.timezone)}</td>
                        <td data-label="Login / device">
                          {row.clock_login_email ?? "No clock-in login"}
                          {row.has_clock_device ? " · device bound" : ""}
                        </td>
                        <td className="row-actions">
                          {canManageHr && !row.on_leave ? (
                            <>
                              <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void mark(row, "PRESENT")}>Present</button>
                              <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void mark(row, "LATE")}>Late</button>
                              <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void mark(row, "ABSENT")}>Absent</button>
                            </>
                          ) : null}
                          {canManageHr && row.has_clock_device ? (
                            <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void unlockDevice(row)}>Unlock device</button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ul className="titles-list">
                  {rows.map((row) => (
                    <li key={row.employee_id} className="titles-row">
                      <Link to={employeeHref(row.employee_id)} className="titles-row-top row-link">
                        <PersonCell name={row.employee_name} email={statusLabel(row.status)} />
                        <StatusPill value={statusLabel(row.status)} />
                      </Link>
                      <p className="muted" style={{ margin: "0.35rem 0 0" }}>
                        In {formatDateTime(row.checked_in_at, branch.timezone)} · Out {formatDateTime(row.checked_out_at, branch.timezone)}
                      </p>
                      {canManageHr ? (
                        <div className="row-actions" style={{ marginTop: "0.5rem" }}>
                          {!row.on_leave ? (
                            <>
                              <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void mark(row, "PRESENT")}>Present</button>
                              <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void mark(row, "LATE")}>Late</button>
                              <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void mark(row, "ABSENT")}>Absent</button>
                            </>
                          ) : null}
                          {row.has_clock_device ? (
                            <button className="btn ghost small" type="button" disabled={busyId === row.employee_id} onClick={() => void unlockDevice(row)}>Unlock device</button>
                          ) : null}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default function AttendancePage() {
  const { token, company, branch, hasPermission } = useWorkspace();
  if (!hasPermission("attendance.manage")) return <MyAttendance />;
  return (
    <AttendanceRegister
      token={token}
      company={company}
      branch={branch}
      canManageHr={hasPermission("attendance.manage")}
      canManageOrg={hasPermission("people.manage")}
      employeeHref={(id) => `/app/people/${id}`}
      addEmployeeHref="/app/people/new"
    />
  );
}
