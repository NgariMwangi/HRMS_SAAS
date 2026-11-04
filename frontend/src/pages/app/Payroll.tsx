import PayslipDocument from "../../components/PayslipDocument";
import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
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
    load().catch(() => undefined);
  }, [company?.id, branch?.id, token, apiBase]);

  const latest = runs[0];
  const open = useMemo(() => runs.find((row) => row.id === openId) ?? latest, [runs, openId, latest]);

  const selectedBounds = useMemo(() => monthBounds(month), [month]);
  const selectedRun = runs.find(
    (row) => row.period_start === selectedBounds.start && row.period_end === selectedBounds.end,
  );
  const selectedApproved = selectedRun?.status === "APPROVED";
  const selectedDraft = selectedRun?.status === "DRAFT";

  async function postPeriod(periodStart: string, periodEnd: string) {
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
        }),
      });
      setRuns((current) => [created, ...current.filter((row) => row.id !== created.id)]);
      setOpenId(created.id);
      setSlipId(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run payroll");
    } finally {
      setBusy(false);
    }
  }

  async function createRun(event: FormEvent) {
    event.preventDefault();
    await postPeriod(selectedBounds.start, selectedBounds.end);
  }

  async function approve(run: PayrollRun) {
    if (!canManageHr) return;
    setBusy(true);
    try {
      const saved = await api<PayrollRun>(apiUrl(apiBase, `/payroll/runs/${run.id}/approve`), { method: "POST", token });
      setRuns((current) => current.map((row) => (row.id === saved.id ? saved : row)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve");
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
          {canManageHr ? (
            <form className="filters" onSubmit={createRun}>
              <label>
                Period
                <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
              </label>
              <button className="btn small" type="submit" disabled={busy || selectedApproved}>
                {busy ? "Running…" : selectedApproved ? "Already approved" : selectedDraft ? "Rerun payroll" : "Run payroll"}
              </button>
            </form>
          ) : null}
          <div className="kpis">
            <Kpi label="Current period" value={open ? `${formatDate(open.period_start)} – ${formatDate(open.period_end)}` : "—"} hint={open ? open.status.toLowerCase() : "No run yet"} />
            <Kpi label="Gross pay" value={formatMoney(open?.gross_total, open?.currency_code)} />
            <Kpi label="Deductions" value={formatMoney(open?.deduction_total, open?.currency_code)} />
            <Kpi label="Net pay" value={formatMoney(open?.net_total, open?.currency_code)} />
          </div>
          <section className="card">
            {runs.length === 0 ? (
              <EmptyState
                title="No payroll runs"
                note="Add salaries on employee records, then run this branch’s period. Statutory amounts come from the country pack."
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
                    {runs.map((row) => (
                      <tr key={row.id}>
                        <td data-label="Period">{formatDate(row.period_start)} – {formatDate(row.period_end)}</td>
                        <td data-label="Status"><StatusPill value={row.status} /></td>
                        <td data-label="Gross">{formatMoney(row.gross_total, row.currency_code)}</td>
                        <td data-label="Net">{formatMoney(row.net_total, row.currency_code)}</td>
                        <td className="row-actions">
                          <button className="btn ghost small" type="button" onClick={() => { setOpenId(row.id); setSlipId(null); }}>Payslips</button>
                          {canManageHr && row.status === "DRAFT" ? (
                            <>
                              <button className="btn ghost small" type="button" disabled={busy} onClick={() => void postPeriod(row.period_start, row.period_end)}>Rerun</button>
                              <button className="btn small" type="button" disabled={busy} onClick={() => void approve(row)}>Approve</button>
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

