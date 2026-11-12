import { FormEvent, useEffect, useState } from "react";
import { brandVariables, CompanyLogo } from "./CompanyBranding";
import { Link } from "react-router-dom";
import { api, apiDownload } from "../api";
import { Card, EmptyState, formatDate, formatDateTime, Kpi, PageHeader, StatusPill, TableSkeleton } from "../ui";
import { generalReports } from "../reportNavigation";
import "../general-reports.css";

type Option = { id: string; name: string };
type Catalog = { company: string; reports: { key: string; title: string; description: string }[]; branches: Option[]; departments: Option[] };
type Column = { key: string; label: string; kind: string };
type Row = Record<string, string | number | null>;
type Breakdown = { title: string; columns: Column[]; rows: Row[] };
type Report = { key: string; title: string; company: string; theme_color?: string; logo_data_url?: string | null; branch: string; department: string; start_on: string; end_on: string; generated_at: string; note: string; selected_status: string; statuses: string[]; summary: { label: string; value: number | string }[]; breakdowns: Breakdown[]; columns: Column[]; rows: Row[]; total_rows: number; page: number; page_size: number };
type Filters = { branch_id: string; department_id: string; start_on: string; end_on: string; status: string; q: string };
const statusOptions: Record<string, string[]> = { headcount: ["ACTIVE", "SUSPENDED", "TERMINATED"], payroll: ["APPROVED", "DRAFT"], attendance: ["PRESENT", "LATE", "ABSENT", "ON_LEAVE"], leave: ["PENDING_SUPERVISOR", "PENDING_HR", "APPROVED", "REJECTED", "CANCELLED"], movement: ["HIRED", "REHIRED", "SUSPENDED", "REINSTATED", "TERMINATED", "ROLE_CHANGED", "EXTENDED"] };
const label = (value: string) => value.toLowerCase().replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
const dateString = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function defaults(kind?: string): Filters { const today = new Date(); return { branch_id: "", department_id: "", start_on: dateString(new Date(today.getFullYear(), today.getMonth(), 1)), end_on: dateString(today), status: kind === "payroll" ? "APPROVED" : "ALL", q: "" }; }
function exactDecimal(value: string | number) { const [integer, fraction] = String(value).split("."); return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction ? `.${fraction}` : ""); }

export default function GeneralReports({ companyId, token, apiBase = "", kind, selectReport, reportHref, employeeHref }: { companyId: string; token: string; apiBase?: string; kind?: string; selectReport: (key?: string) => void; reportHref?: (key?: string) => string; employeeHref?: (id: string) => string }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null); const [report, setReport] = useState<Report | null>(null);
  const [draft, setDraft] = useState<Filters>(() => defaults(kind)); const [applied, setApplied] = useState<Filters>(() => defaults(kind));
  const [page, setPage] = useState(1); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [exporting, setExporting] = useState(false); const [refresh, setRefresh] = useState(0);
  const meta = generalReports.find(r => r.key === kind);
  const base = `${apiBase}/reports`;
  const params = new URLSearchParams({ company_id: companyId, page: String(page), page_size: "50", ...applied });
  if (!applied.branch_id) params.delete("branch_id"); if (!applied.department_id) params.delete("department_id");
  const query = params.toString();
  useEffect(() => { let active = true; setLoading(true); setError("");
    void api<Catalog>(`${base}/catalog?company_id=${companyId}`, { token }).then(value => { if (active) setCatalog(value); }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active && !kind) setLoading(false); });
    return () => { active = false; };
  }, [base, companyId, token, kind, refresh]);
  useEffect(() => {
    if (!kind) return;
    let active = true; setLoading(true); setError(""); setReport(null);
    void api<Report>(`${base}/${kind}?${query}`, { token }).then(value => { if (active) setReport(value); }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [base, companyId, kind, token, query, refresh]);
  function apply(e: FormEvent<HTMLFormElement>) { e.preventDefault(); setPage(1); setApplied({ ...draft }); setRefresh(v => v + 1); }
  function preset(value: string) {
    const today = new Date(); let start = new Date(today.getFullYear(), today.getMonth(), 1); let end = today;
    if (value === "last-month") { start = new Date(today.getFullYear(), today.getMonth() - 1, 1); end = new Date(today.getFullYear(), today.getMonth(), 0); }
    if (value === "quarter") start = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
    if (value === "year") start = new Date(today.getFullYear(), 0, 1);
    setDraft(current => ({ ...current, start_on: dateString(start), end_on: dateString(end) }));
  }
  function cell(value: string | number | null, column: Column, row?: Row) {
    if (value === null || value === "") return "—";
    const text = String(value);
    if (column.kind === "date") return formatDate(text);
    if (column.kind === "datetime") return formatDateTime(text);
    if (column.kind === "decimal" || column.kind === "number") return exactDecimal(value);
    if (column.kind === "status") return <StatusPill value={text.replace(/_/g, " ")} />;
    if (column.key === "employee" && row?.employee_id && employeeHref) return <Link to={employeeHref(String(row.employee_id))}>{text}</Link>;
    return column.key === "label" && /^[A-Z_]+$/.test(text) ? label(text) : text;
  }
  function table(columns: Column[], rows: Row[], title: string) {
    return <div className="table-wrap"><table aria-label={title}><thead><tr>{columns.map(c => <th key={c.key} className={c.kind === "decimal" || c.kind === "number" ? "general-report-numeric" : ""}>{c.label}</th>)}</tr></thead><tbody>{rows.map((r, index) => <tr key={String(r.id || index)}>{columns.map(c => <td key={c.key} data-label={c.label} className={c.kind === "decimal" || c.kind === "number" ? "general-report-numeric" : ""}>{cell(r[c.key], c, r)}</td>)}</tr>)}</tbody></table></div>;
  }
  async function exportCsv() {
    setError(""); setExporting(true);
    try { await apiDownload(`${base}/${kind}/export?${query}`, token, `${kind}-${applied.end_on}.csv`); } catch (e) { setError((e as Error).message); } finally { setExporting(false); }
  }
  async function exportPdf() {
    setError(""); setExporting(true);
    try { await apiDownload(`${base}/${kind}/pdf?${query}`, token, `${kind}-${applied.end_on}.pdf`); } catch (e) { setError((e as Error).message); } finally { setExporting(false); }
  }
  return <div className="general-reports" style={report ? brandVariables(report.theme_color) : undefined}>
    {kind && <div>{reportHref ? <Link className="btn small ghost" to={reportHref()}>← All reports</Link> : <button className="btn small ghost" onClick={() => selectReport()}>← All reports</button>}</div>}
    <PageHeader title={kind ? meta?.title || "Report" : "General reports"} description={meta?.description || "Choose a report to explore your company's records."} actions={kind && report ? <><button className="btn ghost" type="button" onClick={() => setRefresh(v => v + 1)} disabled={loading}>Refresh</button><button className="btn" type="button" disabled={exporting || !report.total_rows || loading} onClick={() => void exportCsv()}>{exporting ? "Exporting…" : "Export CSV"}</button></> : undefined} />
    {error && <div className="error" role="alert">{error} <button className="btn small ghost" onClick={() => setRefresh(v => v + 1)}>Retry</button></div>}
    {!kind && (loading ? <TableSkeleton rows={3} cols={3} /> : catalog?.reports.length ? <><p className="muted">Reports use live records for <strong>{catalog.company}</strong>. Each report has its own filters and export.</p><div className="general-report-library">{catalog.reports.map(r => reportHref ? <Link className="card general-report-choice" key={r.key} to={reportHref(r.key)}><strong>{r.title}<span>→</span></strong><p>{r.description}</p><small>Open report</small></Link> : <button className="card general-report-choice" key={r.key} onClick={() => selectReport(r.key)}><strong>{r.title}<span>→</span></strong><p>{r.description}</p><small>Open report</small></button>)}</div></> : !error && <EmptyState title="No reports available" note="Your role needs General Reports permission and access to the relevant HR module." />)}
    {kind && <>
      <Card title="Filters" padded><form className="general-report-filters" onSubmit={apply}>
        <label>Branch<select value={draft.branch_id} onChange={e => setDraft(d => ({ ...d, branch_id: e.target.value }))}><option value="">All branches</option>{catalog?.branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label>Department<select value={draft.department_id} onChange={e => setDraft(d => ({ ...d, department_id: e.target.value }))}><option value="">All departments</option>{catalog?.departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        {kind !== "headcount" && <><label>From<input type="date" required value={draft.start_on} max={draft.end_on || undefined} onChange={e => setDraft(d => ({ ...d, start_on: e.target.value }))} /></label><label>To<input type="date" required value={draft.end_on} min={draft.start_on || undefined} onChange={e => setDraft(d => ({ ...d, end_on: e.target.value }))} /></label></>}
        <label>{kind === "movement" ? "Change type" : "Status"}<select value={draft.status} onChange={e => setDraft(d => ({ ...d, status: e.target.value }))}><option value="ALL">All {kind === "movement" ? "changes" : "statuses"}</option>{statusOptions[kind]?.map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label>
        <label>Find employee<input type="search" placeholder="Name or employee number" maxLength={100} value={draft.q} onChange={e => setDraft(d => ({ ...d, q: e.target.value }))} /></label>
        <div className="general-report-filter-actions"><div className="actions">{kind !== "headcount" && <label className="general-report-period"><span className="sr-only">Set report period</span><select defaultValue="" onChange={e => { preset(e.target.value); e.target.value = ""; }}><option value="" disabled>Quick date range</option><option value="month">This month</option><option value="last-month">Last month</option><option value="quarter">This quarter</option><option value="year">This year</option></select></label>}<button className="btn" disabled={loading}>Apply filters</button><button className="btn ghost" type="button" disabled={loading} onClick={() => { const values = defaults(kind); setDraft(values); setApplied(values); setPage(1); setRefresh(v => v + 1); }}>Reset</button></div><small>{kind === "headcount" ? "Current records. No historical date filter." : "Summaries and exports use the applied filters."}</small></div>
      </form></Card>
      {loading ? <TableSkeleton rows={6} cols={6} /> : report && <>
        <div className="general-report-context"><CompanyLogo company={{ name: report.company, logo_data_url: report.logo_data_url }} /><span><strong>{report.company}</strong> · {report.branch} · {report.department}</span><span>{kind === "headcount" ? "Current snapshot" : `${formatDate(report.start_on)} – ${formatDate(report.end_on)}`}</span><small>Generated {formatDateTime(report.generated_at)}</small><button type="button" className="btn ghost small" disabled={exporting || loading} onClick={() => void exportPdf()}>{exporting ? "Preparing…" : "Download PDF"}</button></div>
        <div className="general-report-kpis">{report.summary.map(m => <Kpi key={m.label} label={m.label} value={exactDecimal(m.value)} />)}</div>
        <p className="general-report-note">{report.note}</p>
        {!!report.total_rows && <div className="general-report-breakdowns">{report.breakdowns.map(b => <Card key={b.title} title={b.title}>{b.columns.length === 2 ? <div className="general-report-bars">{b.rows.map((r, index) => <div key={index}><span>{cell(r[b.columns[0].key], b.columns[0])}</span><progress aria-label={String(r[b.columns[0].key])} value={Number(r[b.columns[1].key])} max={Math.max(1, ...b.rows.map(row => Number(row[b.columns[1].key])))} /><strong>{r[b.columns[1].key]}</strong></div>)}</div> : table(b.columns, b.rows, b.title)}</Card>)}</div>}
        <Card title={kind === "headcount" ? "Employee records" : "Report records"} note={`${report.total_rows.toLocaleString()} matching records. CSV includes the complete filtered selection.`}>{report.rows.length ? <>{table(report.columns, report.rows, report.title)}<div className="general-report-pagination"><span>Showing {(report.page - 1) * report.page_size + 1}–{Math.min(report.page * report.page_size, report.total_rows)} of {report.total_rows.toLocaleString()}</span><div className="actions"><button className="btn small ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button><span>Page {page} of {Math.max(1, Math.ceil(report.total_rows / report.page_size))}</span><button className="btn small ghost" disabled={page * report.page_size >= report.total_rows} onClick={() => setPage(p => p + 1)}>Next</button></div></div></> : <EmptyState title="No matching records" note="Try another date range, branch, department or status. Existing records are never changed by reports." />}</Card>
      </>}
    </>}
  </div>;
}
