import PayslipDocument from "../../components/PayslipDocument";
import { FormEvent, Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api, apiUrl } from "../../api";
import type { PayrollRun, Payslip } from "../../types";
import { EmptyState, Kpi, KpiRowSkeleton, PageHeader, StatusPill, TableSkeleton, formatDate, formatMoney } from "../../ui";

function monthBounds(value: string): { start: string; end: string } {
  const [year, month] = value.split("-").map(Number);
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    start: `${year}-${pad(month)}-01`,
    end: `${year}-${pad(month)}-${pad(last)}`,
  };
}

function thisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function shiftMonth(value: string, offset: number): string {
  const [year, month] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + offset, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

export type PayrollScope = {
  token: string;
  apiBase?: string;
  company: { id: string; name: string } | null;
  branch: { id: string; name: string } | null;
  canManageHr: boolean;
  settingsHref?: string | null;
  employeeHref: (id: string) => string;
  hideHeader?: boolean;
};

export function PayrollBoard({
  token,
  apiBase = "",
  company,
  branch,
  canManageHr,
  settingsHref,
  employeeHref,
  hideHeader,
}: PayrollScope) {
  const [month, setMonth] = useState(thisMonth);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [slipId, setSlipId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  type Person = { id: string; name: string; employee_number: string; eligible: boolean; skip_reason: string | null };
  const [review, setReview] = useState<{ start: string; end: string; people: Person[]; excluded: string[]; previousExclusions: string[] } | null>(null);
  const [peopleQuery, setPeopleQuery] = useState("");
  const reviewRequest = useRef(0);

  async function load() {
    if (!company || !branch) {
      setRuns([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const list = await api<PayrollRun[]>(
        apiUrl(apiBase, `/payroll/runs?company_id=${company.id}&branch_id=${branch.id}`),
        { token },
      );
      setRuns(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load payroll");
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reviewRequest.current += 1;
    setReview(null);
    setBusy(false);
    setOpenId(null);
    setSlipId(null);
    load().catch(() => undefined);
  }, [company?.id, branch?.id, token, apiBase]);

  const monthRuns = useMemo(() => runs.filter(row => row.period_start.slice(0, 7) === month), [runs, month]);
  const open = useMemo(() => monthRuns.find(row => row.id === openId) ?? monthRuns[0], [monthRuns, openId]);

  function selectMonth(value: string) {
    if (!/^\d{4}-\d{2}$/.test(value)) return;
    setMonth(value); setOpenId(null); setSlipId(null); setReview(null); setPeopleQuery("");
  }

  const selectedBounds = useMemo(() => monthBounds(month), [month]);
  const selectedRun = runs.find(
    (row) => row.period_start === selectedBounds.start && row.period_end === selectedBounds.end,
  );
  const selectedApproved = selectedRun?.status === "APPROVED";
  const selectedDraft = selectedRun?.status === "DRAFT";

  async function preparePeriod(start: string, end: string) {
    if (!company || !branch || !canManageHr) return;
    const request = ++reviewRequest.current;
    setBusy(true); setError(null); setReview(null); setPeopleQuery("");
    try {
      const existing = runs.find(run => run.period_start === start && run.period_end === end);
      const [people, savedRun] = await Promise.all([
        api<Person[]>(apiUrl(apiBase, `/payroll/employees?company_id=${company.id}&branch_id=${branch.id}&period_end=${end}`), { token }),
        existing ? api<PayrollRun>(apiUrl(apiBase, `/payroll/runs/${existing.id}`), { token }) : Promise.resolve(null),
      ]);
      if (request !== reviewRequest.current) return;
      const exclusions = savedRun?.excluded_employee_ids ?? [];
      setReview({ start, end, people, excluded: [...exclusions], previousExclusions: [...exclusions] });
    } catch (err) {
      if (request === reviewRequest.current) setError(err instanceof Error ? err.message : "Could not load employees");
    } finally { if (request === reviewRequest.current) setBusy(false); }
  }

  async function postPeriod(periodStart: string, periodEnd: string, exclusions: string[]) {
    if (!company || !branch || !canManageHr) return;
    setBusy(true);
    try {
      const created = await api<PayrollRun>(apiUrl(apiBase, "/payroll/runs"), {
        method: "POST",
        token,
        body: JSON.stringify({
          company_id: company.id,
          branch_id: branch.id,
          period_start: periodStart,
          period_end: periodEnd,
          excluded_employee_ids: exclusions,
        }),
      });
      setRuns((current) => [created, ...current.filter((row) => row.id !== created.id)]);
      setOpenId(created.id);
      setSlipId(null);
      reviewRequest.current += 1;
      setReview(null);
      setPeopleQuery("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run payroll");
    } finally {
      setBusy(false);
    }
  }

  async function createRun(event: FormEvent) {
    event.preventDefault();
    await preparePeriod(selectedBounds.start, selectedBounds.end);
  }

  async function approve(run: PayrollRun, approved = true) {
    if (!canManageHr) return;
    if (!approved && !window.confirm("Return this payroll to draft? You can edit exclusions and rerun it. Employees will no longer see its payslips until it is approved again. Emails already sent cannot be recalled.")) return;
    setBusy(true);
    try {
      const saved = await api<PayrollRun>(apiUrl(apiBase, `/payroll/runs/${run.id}/${approved ? "approve" : "unapprove"}`), { method: "POST", token });
      setRuns((current) => current.map((row) => (row.id === saved.id ? saved : row)));
      setSlipId(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : approved ? "Could not approve" : "Could not unapprove");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {hideHeader ? null : (
        <PageHeader
          title="Payroll"
          description={`${company?.name ?? "This company"}${branch ? ` · ${branch.name}` : ""}. Runs stay in this branch’s currency and country pack.`}
          actions={settingsHref ? <Link className="btn ghost small" to={settingsHref}>Configuration</Link> : null}
        />
      )}
      {error ? <p className="error">{error}</p> : null}
      {!company || !branch ? (
        <section className="card">
          <EmptyState title="Select a branch" note="Payroll is calculated for the selected company and branch." />
        </section>
      ) : loading ? (
        <>
          <KpiRowSkeleton />
          <section className="card"><TableSkeleton cols={5} /></section>
        </>
      ) : (
        <>
            <form className="filters" onSubmit={createRun}>
              <button className="btn ghost small" type="button" disabled={busy} onClick={() => selectMonth(shiftMonth(month, -1))}>Previous month</button>
              <label>
                Payroll month
                <input type="month" required value={month} disabled={busy} onChange={(event) => selectMonth(event.target.value)} />
              </label>
              <button className="btn ghost small" type="button" disabled={busy} onClick={() => selectMonth(shiftMonth(month, 1))}>Next month</button>
              <label>Saved payrolls
                <select value={open?.id ?? ""} disabled={busy || !runs.length} onChange={event => {
                  const selected = runs.find(run => run.id === event.target.value);
                  if (selected) { selectMonth(selected.period_start.slice(0, 7)); setOpenId(selected.id); }
                }}>
                  <option value="" disabled>Select a saved payroll</option>
                  {runs.map(run => <option key={run.id} value={run.id}>{formatDate(run.period_start)} – {formatDate(run.period_end)} · {run.status.toLowerCase()}</option>)}
                </select>
              </label>
              {canManageHr &&
              <button className="btn small" type="submit" disabled={busy || selectedApproved}>
                {busy ? "Running…" : selectedApproved ? "Already approved" : selectedDraft ? "Rerun payroll" : "Run payroll"}
              </button>}
            </form>
          {canManageHr && review && <section className="card card-pad" aria-label="Review payroll employees">
            <h3>Review employees · {formatDate(review.start)} – {formatDate(review.end)}</h3>
            <p>Tick employees to exclude from this payroll run only. Employees without an applicable salary or with an inactive status are automatically left out.</p>
            {!!review.previousExclusions.length && <p>Previous exclusions are already ticked. Untick an employee to include them in this rerun.</p>}
            <p><strong>{review.people.filter(person => person.eligible && !review.excluded.includes(person.id)).length} to include</strong> ? {review.people.filter(person => person.eligible && review.excluded.includes(person.id)).length} manually excluded ? {review.people.filter(person => !person.eligible).length} automatically left out</p>
            <label>Find employee<input type="search" value={peopleQuery} onChange={event => setPeopleQuery(event.target.value)} placeholder="Name or employee number" /></label>
            <div style={{ maxHeight: 320, overflowY: "auto", margin: "16px 0" }}>
              {review.people.filter(person => `${person.name} ${person.employee_number}`.toLowerCase().includes(peopleQuery.toLowerCase())).map(person => <label key={person.id} style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 12, padding: "8px 0" }}>
                <input style={{ width: "auto" }} type="checkbox" disabled={busy || !person.eligible} checked={!person.eligible || review.excluded.includes(person.id)} onChange={event => { const checked = event.target.checked; setReview(current => current && ({ ...current, excluded: checked ? [...current.excluded, person.id] : current.excluded.filter(id => id !== person.id) })); }} />
                <span><strong>{person.name}</strong> · {person.employee_number}<small style={{ display: "block" }}>{!person.eligible ? `Not included: ${person.skip_reason}` : review.excluded.includes(person.id) ? review.previousExclusions.includes(person.id) ? "Previously excluded — untick to include" : "Not included: excluded for this run" : "Will be included"}</small></span>
              </label>)}
              {!review.people.length && <p>No employees in this branch.</p>}
            </div>
            <div className="row-actions">
              <button className="btn ghost small" disabled={busy} onClick={() => setReview(current => current && ({ ...current, excluded: [] }))}>Clear exclusions</button>
              <button className="btn ghost small" disabled={busy} onClick={() => setReview(null)}>Cancel</button>
              <button className="btn small" disabled={busy} onClick={() => void postPeriod(review.start, review.end, review.excluded)}>{busy ? "Calculating..." : runs.some(run => run.period_start === review.start && run.period_end === review.end) ? "Confirm rerun" : "Confirm payroll run"}</button>
            </div>
          </section>}
          <div className="kpis">
            <Kpi label="Selected period" value={open ? `${formatDate(open.period_start)} – ${formatDate(open.period_end)}` : month} hint={open ? open.status.toLowerCase() : "No run for this month"} />
            <Kpi label="Gross pay" value={formatMoney(open?.gross_total, open?.currency_code)} />
            <Kpi label="Deductions" value={formatMoney(open?.deduction_total, open?.currency_code)} />
            <Kpi label="Net pay" value={formatMoney(open?.net_total, open?.currency_code)} />
          </div>
          <section className="card">
            {monthRuns.length === 0 ? (
              <EmptyState
                title="No payroll for this month"
                note="Choose another month or a saved payroll above. To create this month's payroll, review employees and run it."
              />
            ) : (
              <>
                <table className="org-table">
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Status</th>
                      <th>Gross</th>
                      <th>Net</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {monthRuns.map((row) => (
                      <tr key={row.id}>
                        <td data-label="Period">{formatDate(row.period_start)} – {formatDate(row.period_end)}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td data-label="Gross">{formatMoney(row.gross_total, row.currency_code)}</td>
                        <td data-label="Net">{formatMoney(row.net_total, row.currency_code)}</td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => { setOpenId(row.id); setSlipId(null); }}>Payslips</button>
                          {canManageHr && row.status === "APPROVED" && <button className="btn ghost small" type="button" disabled={busy || !!review} onClick={() => void approve(row, false)}>Unapprove</button>}
                          {canManageHr && row.status === "DRAFT" ? (
                            <>
                              <button className="btn ghost small" type="button" disabled={busy} onClick={() => { setMonth(row.period_start.slice(0, 7)); void preparePeriod(row.period_start, row.period_end); }}>Rerun</button>
                              <button className="btn small" type="button" disabled={busy || !!review} onClick={() => void approve(row)}>Approve</button>
                            </>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {open ? (
                  <div className="card-pad">
                    <h3 style={{ marginTop: 0 }}>Payslips · {open.country_code} pack v{open.pack_version}</h3>
                    {!!open.excluded_employee_ids?.length && <p className="muted">{open.excluded_employee_ids.length} employees excluded from this run.</p>}
                    {open.skipped ? <p className="muted">{open.skipped} people skipped because they have no salary.</p> : null}
                    <table className="org-table">
                      <thead>
                        <tr>
                          <th>Employee</th>
                          <th>Gross</th>
                          <th>Deductions</th>
                          <th>Net</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {open.payslips.map((slip) => (
                          <Fragment key={slip.id}>
                            <tr>
                              <td data-label="Employee">
                                <Link className="row-link" to={employeeHref(slip.employee_id)}>{slip.employee_name}</Link>
                              </td>
                              <td data-label="Gross">{formatMoney(slip.gross, open.currency_code)}</td>
                              <td data-label="Deductions">{formatMoney(slip.employee_deductions, open.currency_code)}</td>
                              <td data-label="Net">
                                {formatMoney(slip.net, open.currency_code)}
                                {belowOneThird(slip) ? (
                                  <span className="error" title="Kenya Employment Act s.19(3): total deductions should not exceed two-thirds of wages.">
                                    {" "}· below ⅓ of gross
                                  </span>
                                ) : null}
                              </td>
                              <td className="row-actions">
                                <button
                                  className="btn ghost small"
                                  type="button"
                                  aria-expanded={slipId === slip.id}
                                  onClick={() => setSlipId((current) => (current === slip.id ? null : slip.id))}
                                >
                                  {slipId === slip.id ? "Hide payslip" : "View / download payslip"}
                                </button>
                              </td>
                            </tr>
                            {slipId === slip.id ? (
                              <tr>
                                <td colSpan={5} style={{ paddingTop: 0 }}>
                                  <PayslipDocument path={apiUrl(apiBase, `/payroll/payslips/${slip.id}`)} token={token} />
                                </td>
                              </tr>
                            ) : null}
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                    {slipId ? null : (
                      <p className="muted">Open a payslip to view earnings, deductions and employer contributions, or download a PDF copy.</p>
                    )}
                  </div>
                ) : null}
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}

export default function PayrollPage() {
  const { token, company, branch, hasPermission } = useWorkspace();
  return (
    <PayrollBoard
      token={token}
      company={company}
      branch={branch}
      canManageHr={hasPermission("payroll.manage")}
      settingsHref="/app/payroll/settings"
      employeeHref={(id) => `/app/people/${id}${hasPermission("people.view_all") || hasPermission("people.manage") ? "" : "/salary"}`}
    />
  );
}

function belowOneThird(slip: Payslip): boolean {
  return Number(slip.net) * 3 < Number(slip.gross);
}

