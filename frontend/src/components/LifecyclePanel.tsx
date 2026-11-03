import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiUploadFiles, viewDocument } from "../api";
import { DocumentPreview } from "./DocumentPreview";
import {
  suspensionPayText,
  type Branch,
  type Department,
  type Employee,
  type JobTitle,
  type LifecycleActionResult,
  type LifecycleAttachment,
  type LifecycleEvent,
} from "../types";
import { formatDate, StatusPill } from "../ui";

type Action = "SUSPENDED" | "REINSTATED" | "ROLE_CHANGED" | "TERMINATED" | "REHIRED" | "EXTENDED";
const EXTENDABLE = new Set(["INTERN", "CONTRACT"]);

const ATTACHABLE = new Set<Action>(["SUSPENDED", "ROLE_CHANGED", "TERMINATED", "EXTENDED"]);
const REQUIRED_PERIOD_TYPES = new Set(["INTERN", "PROBATION"]);
const END_DATE_TYPES = new Set(["INTERN", "PROBATION", "CONTRACT"]);
const ACCEPT = ".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.txt";
const MAX_FILES = 5;
const MAX_BYTES = 50 * 1024 * 1024;

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function daysBetween(start: string, end: string): string {
  if (!start || !end) return "";
  const from = new Date(`${start}T00:00:00`);
  const to = new Date(`${end}T00:00:00`);
  return String(Math.round((to.getTime() - from.getTime()) / 86400000));
}

function extensionKind(row: LifecycleEvent): string {
  if (row.employment_type === "INTERN") return "Internship";
  if (row.employment_type === "CONTRACT") return "Contract";
  return "Period";
}

export function extensionDetail(row: LifecycleEvent): string {
  const kind = extensionKind(row);
  const until = row.to_date_ended ? formatDate(row.to_date_ended) : "";
  if (row.reason === "DAYS" && row.extension_days) {
    return until
      ? `${kind} extended by ${row.extension_days} days to ${until}.`
      : `${kind} extended by ${row.extension_days} days.`;
  }
  if (until && row.from_date_ended) {
    return `${kind} extended until ${until} (was ${formatDate(row.from_date_ended)}).`;
  }
  if (until) return `${kind} extended until ${until}.`;
  return `${kind} extended.`;
}

function eventLabel(row: LifecycleEvent): string {
  if (row.event_type === "HIRED") return "Employed";
  if (row.event_type === "SUSPENDED") return "Suspended";
  if (row.event_type === "REINSTATED") return "Unsuspended";
  if (row.event_type === "TERMINATED") return "Terminated";
  if (row.event_type === "EXTENDED") return `${extensionKind(row)} extended`;
  if (row.event_type === "REHIRED") return row.reason === "NEW_RECORD" ? "Rehired as new record" : "Rehired";
  if (row.reason === "PROMOTION") return "Promoted";
  if (row.reason === "DEMOTION") return "Demoted";
  if (row.reason === "DEPARTMENT_CHANGE") return "Department changed";
  if (row.reason === "TITLE_CHANGE") return "Job title changed";
  return "Role changed";
}

export function EventDocuments({
  event,
  token,
  apiBase,
}: {
  event: LifecycleEvent;
  token: string;
  apiBase: string;
}) {
  const files = event.attachments ?? [];
  const [viewing, setViewing] = useState<LifecycleAttachment | null>(null);
  if (files.length === 0) return null;

  return (
    <>
      <div className="doc-list">
        {files.map((item) => (
          <button
            key={item.id}
            className="doc-chip"
            type="button"
            onClick={() => viewDocument(
              `${apiBase}/employees/${event.employee_id}/lifecycle/${event.id}/attachments/${item.id}`,
              token,
              item.filename,
              () => setViewing(item),
            )}
          >
            {item.filename}
          </button>
        ))}
      </div>
      {viewing ? (
        <DocumentPreview
          path={`${apiBase}/employees/${event.employee_id}/lifecycle/${event.id}/attachments/${viewing.id}`}
          filename={viewing.filename}
          contentType={viewing.content_type}
          token={token}
          onClose={() => setViewing(null)}
        />
      ) : null}
    </>
  );
}

export function LifecycleTimeline({
  events,
  departments,
  titles,
  profilePath,
  token,
  apiBase,
}: {
  events: LifecycleEvent[];
  departments: Department[];
  titles: JobTitle[];
  profilePath?: (employeeId: string) => string;
  token: string;
  apiBase: string;
}) {
  const dept = new Map(departments.map((row) => [row.id, row.name]));
  const title = new Map(titles.map((row) => [row.id, row.name]));
  if (events.length === 0) {
    return <p className="muted card-pad">No lifecycle events yet.</p>;
  }
  return (
    <table className="life-table">
      <thead>
        <tr>
          <th>Event</th>
          <th>Effective</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {events.map((row) => (
          <tr key={row.id}>
            <td data-label="Event"><StatusPill value={eventLabel(row)} /></td>
            <td data-label="Effective">{formatDate(row.effective_on)}</td>
            <td data-label="Detail">
              {row.event_type === "EXTENDED" ? `${extensionDetail(row)} ` : null}
              {row.event_type === "SUSPENDED" && suspensionPayText(row) ? `${suspensionPayText(row)}. ` : null}
              {row.reason && row.event_type !== "ROLE_CHANGED" && row.event_type !== "REHIRED" ? `${row.reason}. ` : null}
              {row.to_job_title_id && row.to_job_title_id !== row.from_job_title_id
                ? `Title: ${title.get(row.to_job_title_id) ?? "Updated"}. `
                : null}
              {row.to_department_id && row.to_department_id !== row.from_department_id
                ? `Department: ${dept.get(row.to_department_id) ?? "Updated"}. `
                : null}
              {row.note ? row.note : null}
              {row.related_employee_id && profilePath ? (
                <>
                  {" "}
                  <Link className="row-link" to={profilePath(row.related_employee_id)}>Open linked record</Link>
                </>
              ) : null}
              <EventDocuments event={row} token={token} apiBase={apiBase} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LifecycleActions({
  employee,
  token,
  apiBase,
  departments,
  titles,
  branches,
  canAct,
  onChanged,
}: {
  employee: Employee;
  token: string;
  apiBase: string;
  departments: Department[];
  titles: JobTitle[];
  branches: Branch[];
  canAct: boolean;
  onChanged: (result: LifecycleActionResult) => void;
}) {
  const [action, setAction] = useState<Action | null>(null);
  const [rehireMode, setRehireMode] = useState<"SAME_RECORD" | "NEW_RECORD">("SAME_RECORD");
  const [effectiveOn, setEffectiveOn] = useState(today());
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [departmentId, setDepartmentId] = useState(employee.department_id ?? "");
  const [titleId, setTitleId] = useState(employee.job_title_id ?? "");
  const [branchId, setBranchId] = useState(employee.branch_id);
  const [files, setFiles] = useState<File[]>([]);
  const [payTreatment, setPayTreatment] = useState<"WITH_PAY" | "WITHOUT_PAY" | "PARTIAL">("WITH_PAY");
  const [deductionPercent, setDeductionPercent] = useState("");
  const [employmentType, setEmploymentType] = useState(employee.employment_type);
  const [dateJoined, setDateJoined] = useState(today());
  const [periodDays, setPeriodDays] = useState("");
  const [dateEnded, setDateEnded] = useState("");
  const [extendMode, setExtendMode] = useState<"DAYS" | "UNTIL_DATE">("DAYS");
  const [extensionDays, setExtensionDays] = useState("");
  const [extendUntil, setExtendUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDepartmentId(employee.department_id ?? "");
    setTitleId(employee.job_title_id ?? "");
    setBranchId(employee.branch_id);
  }, [employee.department_id, employee.job_title_id, employee.branch_id]);

  if (!canAct) return null;

  const buttons: { action: Action; label: string; warn?: boolean }[] = [];
  if (employee.status === "ACTIVE") {
    buttons.push({ action: "SUSPENDED", label: "Suspend" });
    buttons.push({ action: "ROLE_CHANGED", label: "Change role" });
    if (EXTENDABLE.has(employee.employment_type)) {
      buttons.push({ action: "EXTENDED", label: employee.employment_type === "INTERN" ? "Extend internship" : "Extend contract" });
    }
    buttons.push({ action: "TERMINATED", label: "Terminate", warn: true });
  } else if (employee.status === "SUSPENDED") {
    buttons.push({ action: "REINSTATED", label: "Unsuspend" });
    if (EXTENDABLE.has(employee.employment_type)) {
      buttons.push({ action: "EXTENDED", label: employee.employment_type === "INTERN" ? "Extend internship" : "Extend contract" });
    }
    buttons.push({ action: "TERMINATED", label: "Terminate", warn: true });
  } else if (employee.status === "TERMINATED") {
    buttons.push({ action: "REHIRED", label: "Rehire" });
  }

  function open(next: Action) {
    setAction(next);
    setError(null);
    setEffectiveOn(today());
    setReason(next === "ROLE_CHANGED" ? "PROMOTION" : "");
    setNote("");
    setFiles([]);
    setPayTreatment("WITH_PAY");
    setDeductionPercent("");
    setEmploymentType(employee.employment_type);
    setDateJoined(today());
    setPeriodDays("");
    setDateEnded("");
    setExtendMode("DAYS");
    setExtensionDays("");
    setExtendUntil(employee.date_ended ?? "");
    setRehireMode("SAME_RECORD");
  }

  function changeEmploymentType(value: string) {
    setEmploymentType(value);
    if (!END_DATE_TYPES.has(value)) {
      setPeriodDays("");
      setDateEnded("");
    }
  }

  function changeRehireStart(value: string) {
    setDateJoined(value);
    if (periodDays) {
      const days = Number(periodDays);
      if (Number.isFinite(days) && days >= 0 && value) setDateEnded(addDays(value, days));
    } else if (value && dateEnded) {
      setPeriodDays(daysBetween(value, dateEnded));
    }
  }

  function changeRehireDays(value: string) {
    setPeriodDays(value);
    const days = Number(value);
    if (Number.isFinite(days) && days >= 0 && dateJoined) setDateEnded(addDays(dateJoined, days));
  }

  function changeRehireEnd(value: string) {
    setDateEnded(value);
    setPeriodDays(daysBetween(dateJoined, value));
  }

  function chooseFiles(list: FileList | null) {
    const next = Array.from(list ?? []);
    if (next.length > MAX_FILES) {
      setError(`Attach at most ${MAX_FILES} documents`);
      return;
    }
    if (next.some((item) => item.size > MAX_BYTES)) {
      setError("Each document must be 50 MB or smaller");
      return;
    }
    setError(null);
    setFiles(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!action) return;
    const body: Record<string, unknown> = {
      event_type: action,
      effective_on: effectiveOn,
      note: note.trim() || null,
    };
    if (action === "SUSPENDED" || action === "REINSTATED" || action === "TERMINATED") {
      body.reason = reason.trim();
    }
    if (action === "EXTENDED") {
      body.reason = extendMode;
      if (extendMode === "DAYS") {
        const days = Number(extensionDays);
        if (!extensionDays || !Number.isFinite(days) || days < 1) {
          setError("Enter how many days to extend");
          return;
        }
        body.extension_days = days;
      } else {
        if (!extendUntil) {
          setError("Pick the new end date");
          return;
        }
        if (employee.date_ended && extendUntil <= employee.date_ended) {
          setError("The new end date must be after the current end date");
          return;
        }
        body.date_ended = extendUntil;
      }
    }
    if (action === "SUSPENDED") {
      body.pay_treatment = payTreatment;
      if (payTreatment === "PARTIAL") {
        const percent = Number(deductionPercent);
        if (!deductionPercent || Number.isNaN(percent) || percent <= 0 || percent >= 100) {
          setError("Enter a deduction between 0 and 100 percent");
          return;
        }
        body.pay_deduction_percent = percent;
      }
    }
    setBusy(true);
    setError(null);
    if (action === "ROLE_CHANGED") {
      body.reason = reason;
      body.department_id = departmentId || null;
      body.job_title_id = titleId || null;
      body.branch_id = branchId || null;
    }
    if (action === "REHIRED") {
      body.rehire_mode = rehireMode;
      body.copy_from_previous = rehireMode === "NEW_RECORD";
      body.department_id = departmentId || null;
      body.job_title_id = titleId || null;
      body.branch_id = branchId || null;
      body.employment_type = employmentType;
      if (END_DATE_TYPES.has(employmentType)) {
        if (REQUIRED_PERIOD_TYPES.has(employmentType) && (!dateJoined || !dateEnded)) {
          setError("Intern and probation records need a start date and an end date");
          return;
        }
        if (dateEnded && dateJoined && dateEnded < dateJoined) {
          setError("End date must be on or after the start date");
          return;
        }
        if (dateJoined) body.date_joined = dateJoined;
        body.date_ended = dateEnded || null;
      }
    }
    try {
      let result = await api<LifecycleActionResult>(`${apiBase}/employees/${employee.id}/lifecycle`, {
        method: "POST",
        token,
        body: JSON.stringify(body),
      });
      if (ATTACHABLE.has(action) && files.length > 0) {
        const attachments = await apiUploadFiles<LifecycleAttachment[]>(
          `${apiBase}/employees/${employee.id}/lifecycle/${result.event.id}/attachments`,
          files,
          token,
        );
        result = { ...result, event: { ...result.event, attachments } };
      }
      setAction(null);
      setFiles([]);
      onChanged(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save lifecycle event");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="actions" style={{ marginBottom: action ? 12 : 0 }}>
        {buttons.map((item) => (
          <button
            key={item.action}
            className={`btn small${item.warn ? " warn" : item.action === "SUSPENDED" ? " ghost" : ""}`}
            type="button"
            onClick={() => open(item.action)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {action ? (
        <form className="nested-block" onSubmit={submit} style={{ marginBottom: 16 }}>
          <h3 style={{ margin: "0 0 10px", fontSize: "1rem" }}>
            {action === "SUSPENDED" ? "Suspend" : action === "REINSTATED" ? "Unsuspend" : action === "ROLE_CHANGED" ? "Change role" : action === "TERMINATED" ? "Terminate" : action === "EXTENDED" ? (employee.employment_type === "INTERN" ? "Extend internship" : "Extend contract") : "Rehire"}
          </h3>
          <div className="form-grid">
            <label>Effective date<input required type="date" value={effectiveOn} onChange={(event) => setEffectiveOn(event.target.value)} /></label>
            {action === "ROLE_CHANGED" ? (
              <label>Reason
                <select value={reason} onChange={(event) => setReason(event.target.value)}>
                  <option value="PROMOTION">Promotion</option>
                  <option value="DEMOTION">Demotion</option>
                  <option value="TITLE_CHANGE">Job title change</option>
                  <option value="DEPARTMENT_CHANGE">Department change</option>
                </select>
              </label>
            ) : action !== "REHIRED" && action !== "EXTENDED" ? (
              <label>Reason<input required value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required" /></label>
            ) : action === "REHIRED" ? (
              <label>How to rehire
                <select value={rehireMode} onChange={(event) => setRehireMode(event.target.value as "SAME_RECORD" | "NEW_RECORD")}>
                  <option value="SAME_RECORD">Continue this record</option>
                  <option value="NEW_RECORD">Create a new employee record</option>
                </select>
              </label>
            ) : (
              <>
                <label>How to extend
                  <select value={extendMode} onChange={(event) => setExtendMode(event.target.value as "DAYS" | "UNTIL_DATE")}>
                    <option value="DAYS">By an agreed number of days</option>
                    <option value="UNTIL_DATE">Until a specific date</option>
                  </select>
                </label>
                {extendMode === "DAYS" ? (
                  <label>Days to add
                    <input required type="number" min={1} step={1} value={extensionDays} onChange={(event) => setExtensionDays(event.target.value)} placeholder="e.g. 90" />
                    <small className="muted">
                      {extensionDays && Number(extensionDays) > 0
                        ? `New end date: ${addDays(employee.date_ended || effectiveOn, Number(extensionDays))}.`
                        : `Counted from ${employee.date_ended ? "the current end date" : "the effective date"}.`}
                    </small>
                  </label>
                ) : (
                  <label>New end date
                    <input
                      required
                      type="date"
                      min={employee.date_ended || employee.date_joined || undefined}
                      value={extendUntil}
                      onChange={(event) => setExtendUntil(event.target.value)}
                    />
                  </label>
                )}
              </>
            )}
            {action === "SUSPENDED" ? (
              <>
                <label>Pay during suspension
                  <select value={payTreatment} onChange={(event) => setPayTreatment(event.target.value as "WITH_PAY" | "WITHOUT_PAY" | "PARTIAL")}>
                    <option value="WITH_PAY">With pay</option>
                    <option value="WITHOUT_PAY">Without pay</option>
                    <option value="PARTIAL">Deduct a percentage</option>
                  </select>
                </label>
                {payTreatment === "PARTIAL" ? (
                  <label>Percentage deducted
                    <input
                      required
                      type="number"
                      min="0.01"
                      max="99.99"
                      step="0.01"
                      value={deductionPercent}
                      onChange={(event) => setDeductionPercent(event.target.value)}
                      placeholder="e.g. 25"
                    />
                    <small className="muted">Recorded for payroll. Not applied until a payroll run uses it.</small>
                  </label>
                ) : null}
              </>
            ) : null}
            {action === "ROLE_CHANGED" || action === "REHIRED" ? (
              <>
                <label>Department
                  <select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}>
                    <option value="">None</option>
                    {departments.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </select>
                </label>
                <label>Job title
                  <select value={titleId} onChange={(event) => setTitleId(event.target.value)}>
                    <option value="">None</option>
                    {titles.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </select>
                </label>
                <label>Branch
                  <select value={branchId} onChange={(event) => setBranchId(event.target.value)}>
                    {branches.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </select>
                </label>
                {action === "REHIRED" ? (
                  <>
                    <label>Employment type
                      <select value={employmentType} onChange={(event) => changeEmploymentType(event.target.value)}>
                        <option value="FULL_TIME">Full-time</option>
                        <option value="CONTRACT">Contract</option>
                        <option value="INTERN">Intern</option>
                        <option value="PROBATION">Probation</option>
                      </select>
                    </label>
                    {END_DATE_TYPES.has(employmentType) ? (
                      <>
                        <label>Start date<input required={REQUIRED_PERIOD_TYPES.has(employmentType)} type="date" value={dateJoined} onChange={(event) => changeRehireStart(event.target.value)} /></label>
                        <label>Duration (days)<input type="number" min={0} step={1} value={periodDays} onChange={(event) => changeRehireDays(event.target.value)} placeholder="e.g. 90" /></label>
                        <label>End date<input required={REQUIRED_PERIOD_TYPES.has(employmentType)} type="date" min={dateJoined || undefined} value={dateEnded} onChange={(event) => changeRehireEnd(event.target.value)} /></label>
                        <p className="muted" style={{ gridColumn: "1 / -1" }}>
                          {REQUIRED_PERIOD_TYPES.has(employmentType)
                            ? "Intern and probation need a start date and an end date. Enter the days, or pick the end date on the calendar."
                            : "End date is optional for contract. Enter the days, or pick the end date on the calendar."}
                        </p>
                      </>
                    ) : null}
                  </>
                ) : null}
              </>
            ) : null}
            <label style={{ gridColumn: "1 / -1" }}>Note<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
            {ATTACHABLE.has(action) ? (
              <label style={{ gridColumn: "1 / -1" }}>
                Attach documents
                <input
                  type="file"
                  accept={ACCEPT}
                  multiple
                  onChange={(event) => chooseFiles(event.target.files)}
                />
                <small className="muted">
                  Optional. PDF, Word, image, or text. 50 MB each, up to {MAX_FILES} files.
                  {files.length ? ` ${files.length} selected.` : ""}
                </small>
              </label>
            ) : null}
          </div>
          {action === "REHIRED" && rehireMode === "NEW_RECORD" ? (
            <p className="muted">A new employee number is issued. Personal details are copied. The same work email can be reused.</p>
          ) : null}
          {error ? <p className="error">{error}</p> : null}
          <div className="actions">
            <button className="btn ghost" type="button" onClick={() => setAction(null)}>Cancel</button>
            <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </div>
        </form>
      ) : null}
    </>
  );
}
