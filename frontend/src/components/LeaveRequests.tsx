import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, apiUrl } from "../api";
import {
  countLeaveDays,
  employeeName,
  formatLeaveDays,
  leaveRequestedAsLabel,
  leaveStatusLabel,
  type LeavePerson,
  type LeaveBalance,
  type LeaveRequest,
  type LeaveType,
  type Supervisor,
} from "../types";
import { IconPlus } from "./icons";
import { EmptyState, formatDate, StatusPill } from "../ui";

export function LeaveRequests({
  token,
  apiBase = "",
  companyId,
  employees,
  types,
  canManageHr,
  selfEmployeeId,
  canManageTeam = false,
  supervisorEmployeeId = selfEmployeeId,
  ownOnly = false,
  notify,
}: {
  token: string;
  apiBase?: string;
  companyId: string;
  employees: LeavePerson[];
  types: LeaveType[];
  canManageHr: boolean;
  selfEmployeeId?: string | null;
  canManageTeam?: boolean;
  supervisorEmployeeId?: string | null;
  ownOnly?: boolean;
  notify: (message: string) => void;
}) {
  const [rows, setRows] = useState<LeaveRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [employeeId, setEmployeeId] = useState("");
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [startOn, setStartOn] = useState("");
  const [endOn, setEndOn] = useState("");
  const [duration, setDuration] = useState("FULL_DAY");
  const [reason, setReason] = useState("");
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [balance, setBalance] = useState<LeaveBalance | null>(null);

  const people = useMemo(
    () =>
      employees
        .filter((row) => row.status !== "TERMINATED")
        .sort((a, b) => employeeName(a).localeCompare(employeeName(b))),
    [employees],
  );
  const chosenType = types.find((row) => row.id === leaveTypeId);
  const wholeDays = countLeaveDays(startOn, endOn, chosenType?.day_basis ?? "WORKING");
  const days = wholeDays ? duration === "HALF_DAY" ? 0.5 : duration === "QUARTER_DAY" ? 0.25 : wholeDays : 0;

  async function load() {
    const list = await api<LeaveRequest[]>(apiUrl(apiBase, `/leave-requests?company_id=${companyId}${ownOnly && selfEmployeeId ? `&employee_id=${selfEmployeeId}` : ""}`), { token });
    setRows(list);
  }

  useEffect(() => {
    setLoading(true);
    load()
      .then(() => setError(null))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [companyId, token, apiBase, ownOnly, selfEmployeeId]);

  useEffect(() => {
    if (!employeeId || !token) {
      setSupervisors([]);
      return;
    }
    api<Supervisor[]>(apiUrl(apiBase, `/employees/${employeeId}/supervisors`), { token })
      .then(setSupervisors)
      .catch(() => setSupervisors([]));
  }, [employeeId, token, apiBase]);

  useEffect(() => {
    if (!employeeId || !leaveTypeId || !token) {
      setBalance(null);
      return;
    }
    const year = startOn ? Number(startOn.slice(0, 4)) : new Date().getFullYear();
    api<LeaveBalance[]>(
      apiUrl(apiBase, `/leave-balances?company_id=${companyId}&employee_id=${employeeId}&leave_type_id=${leaveTypeId}&year=${year}`),
      { token },
    )
      .then((list) => setBalance(list[0] ?? null))
      .catch(() => setBalance(null));
  }, [companyId, employeeId, leaveTypeId, startOn, token, apiBase]);

  function resetForm() {
    setShowForm(false);
    setEmployeeId("");
    setLeaveTypeId("");
    setStartOn("");
    setEndOn("");
    setDuration("FULL_DAY");
    setReason("");
    setError(null);
  }

  async function submit(hrAction: "APPROVE_NOW" | "SEND_TO_SUPERVISOR") {
    if ((!canManageHr && !selfEmployeeId) || !employeeId || !leaveTypeId || !startOn || !endOn) return;
    if (endOn < startOn) {
      setError("End date cannot be before the start date");
      return;
    }
    if (hrAction === "SEND_TO_SUPERVISOR" && supervisors.length === 0) {
      setError("This employee has no supervisor. Approve the leave now, or add a supervisor first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await api<LeaveRequest>(apiUrl(apiBase, canManageHr ? "/leave-requests/hr" : "/leave-requests/self"), {
        method: "POST",
        token,
        body: JSON.stringify({
          employee_id: employeeId,
          leave_type_id: leaveTypeId,
          start_on: startOn,
          end_on: endOn,
          duration,
          reason: reason.trim() || null,
          hr_action: hrAction,
          approval_mode: hrAction === "SEND_TO_SUPERVISOR" ? "SUPERVISOR_THEN_HR" : "HR_ONLY",
        }),
      });
      setRows((current) => [saved, ...current]);
      notify(canManageHr && hrAction === "APPROVE_NOW" ? "Leave approved." : "Leave request submitted.");
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit leave request");
    } finally {
      setBusy(false);
    }
  }

  async function decide(row: LeaveRequest, decision: "APPROVED" | "REJECTED") {
    if (!canManageHr && (!canManageTeam || !supervisorEmployeeId || row.employee_id === supervisorEmployeeId)) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<LeaveRequest>(apiUrl(apiBase, `/leave-requests/${row.id}/${canManageHr ? "hr-decision" : "supervisor-decision"}`), {
        method: "POST",
        token,
        body: JSON.stringify({ decision, supervisor_employee_id: supervisorEmployeeId }),
      });
      setRows((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      notify(decision === "APPROVED" ? "Leave approved." : "Leave rejected.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update leave request");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(row: LeaveRequest) {
    if (!canManageHr) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<LeaveRequest>(apiUrl(apiBase, `/leave-requests/${row.id}/cancel`), {
        method: "POST",
        token,
      });
      setRows((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      notify("Leave request cancelled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel leave request");
    } finally {
      setBusy(false);
    }
  }

  function onCreate(event: FormEvent) {
    event.preventDefault();
  }

  const pending = (status: string) => status === "PENDING_HR" || status === "PENDING_SUPERVISOR";

  return (
    <div>
      <div className="card-head">
        <div>
          <h3>Leave requests</h3>
          <p>{canManageHr ? "Apply for employees and manage HR approvals." : "Request your own leave and track approvals."}</p>
        </div>
        {(canManageHr || selfEmployeeId) && !showForm ? (
          <button className="btn small" type="button" onClick={() => { setShowForm(true); setEmployeeId(canManageHr ? "" : selfEmployeeId ?? ""); setError(null); }} style={{ flexShrink: 0 }}>
            <IconPlus /> {canManageHr ? "Apply for employee" : "Request leave"}
          </button>
        ) : null}
      </div>
      {(canManageHr || selfEmployeeId) && showForm ? (
        <form className="nested-block" onSubmit={onCreate} style={{ margin: "1rem 1.1rem 0" }}>
          <div className="form-grid">
            <label>
              Employee
              <select required disabled={!canManageHr} value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}>
                <option value="">Select</option>
                {people.filter((row) => canManageHr || row.id === selfEmployeeId).map((row) => (
                  <option key={row.id} value={row.id}>{employeeName(row)} · {row.employee_number}</option>
                ))}
              </select>
            </label>
            <label>
              Leave type
              <select required value={leaveTypeId} onChange={(event) => setLeaveTypeId(event.target.value)}>
                <option value="">Select</option>
                {types.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label>Duration<select value={duration} onChange={event => { setDuration(event.target.value); if (event.target.value !== "FULL_DAY") setEndOn(startOn); }}><option value="FULL_DAY">Full day(s)</option><option value="HALF_DAY">Half day (0.5)</option><option value="QUARTER_DAY">Quarter day (0.25)</option></select></label>
            <label>Start<input required type="date" value={startOn} onChange={(event) => { setStartOn(event.target.value); if (duration !== "FULL_DAY") setEndOn(event.target.value); }} /></label>
            <label>End<input required type="date" disabled={duration !== "FULL_DAY"} min={startOn || undefined} value={endOn} onChange={(event) => setEndOn(event.target.value)} /></label>
            <label>Days<input readOnly value={days || ""} placeholder="—" /></label>
            <label style={{ gridColumn: "1 / -1" }}>
              Reason
              <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Optional" />
            </label>
          </div>
          {employeeId && supervisors.length === 0 ? (
            <p className="muted" style={{ margin: "10px 0 0" }}>No supervisor is assigned. Use HR approval.</p>
          ) : null}
          {employeeId && supervisors.length > 0 ? (
            <p className="muted" style={{ margin: "10px 0 0" }}>
              Supervisor{supervisors.length > 1 ? "s" : ""}: {supervisors.map((row) => employeeName(row)).join(", ")}
            </p>
          ) : null}
          {balance ? (
            <p className="muted" style={{ margin: "10px 0 0" }}>
              Remaining this year: {formatLeaveDays(balance.remaining, balance.unlimited)}
              {balance.unlimited ? "" : ` · Used ${formatLeaveDays(balance.used)} · Pending ${formatLeaveDays(balance.pending)}`}
            </p>
          ) : null}
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn small" type="button" disabled={busy} onClick={() => void submit("APPROVE_NOW")}>
              {busy ? "Saving…" : canManageHr ? "Approve now" : "Send to HR"}
            </button>
            <button
              className="btn ghost small"
              type="button"
              disabled={busy || supervisors.length === 0}
              onClick={() => void submit("SEND_TO_SUPERVISOR")}
            >
              Send to supervisor
            </button>
            <button className="btn ghost small" type="button" onClick={resetForm}>Cancel</button>
          </div>
        </form>
      ) : null}
      {error ? <p className="error" style={{ margin: "0.75rem 1.1rem 0" }}>{error}</p> : null}
      {loading ? (
        <p className="muted card-pad">Loading requests…</p>
      ) : rows.length === 0 ? (
        <EmptyState title="No leave requests" note="Apply leave for an employee, or wait for portal requests." />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Type</th>
              <th>Dates</th>
              <th>Days</th>
              <th>From</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Employee">
                  {row.employee_name}
                  <div className="muted">{row.employee_number}</div>
                </td>
                <td data-label="Type">{row.leave_type_name}</td>
                <td data-label="Dates">{formatDate(row.start_on)} – {formatDate(row.end_on)}</td>
                <td data-label="Days">{Number(row.days) === 0.5 ? "Half day (0.5)" : Number(row.days) === 0.25 ? "Quarter day (0.25)" : Number(row.days)}</td>
                <td data-label="From">{leaveRequestedAsLabel(row.requested_as)}</td>
                <td data-label="Status"><StatusPill value={leaveStatusLabel(row.status)} /></td>
                <td className="row-actions">
                  {(canManageHr && pending(row.status)) || (canManageTeam && supervisorEmployeeId && row.employee_id !== supervisorEmployeeId && row.status === "PENDING_SUPERVISOR") ? (
                    <>
                      <button className="btn small" type="button" disabled={busy} onClick={() => void decide(row, "APPROVED")}>Approve</button>
                      <button className="btn ghost small" type="button" disabled={busy} onClick={() => void decide(row, "REJECTED")}>Reject</button>
                      {canManageHr ? <button className="btn ghost small" type="button" disabled={busy} onClick={() => void cancel(row)}>Cancel</button> : null}
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
