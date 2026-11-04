import { useEffect, useState } from "react";
import { api, apiDownload } from "../api";
import { formatDate, TableSkeleton } from "../ui";
import "../payslip.css";

type Line = { id: string; name: string; amount: string };
type Document = { id: string; reference: string; filename: string; employee_name: string; employee_number: string;
  pin_number?: string | null; shif_no?: string | null; nssf_no?: string | null;
  company_name: string; company_legal_name: string | null; company_email: string | null; company_phone: string | null;
  branch_name: string; period_start: string; period_end: string; status: string; currency_code: string; decimal_places: number;
  gross: string; employee_deductions: string; employer_contributions: string; net: string; taxable: string | null;
  earnings: Line[]; deductions: Line[]; employer: Line[] };

function readDocument(value: unknown): Document {
  const data = value as Partial<Document> | null;
  const textFields = ["id", "reference", "filename", "employee_name", "employee_number", "company_name", "branch_name", "period_start", "period_end", "status", "currency_code"] as const;
  const isAmount = (amount: unknown) => typeof amount === "string" && /^-?\d+(\.\d+)?$/.test(amount);
  const validLines = (rows: unknown) => Array.isArray(rows) && rows.every(row => row && typeof row.id === "string" && typeof row.name === "string" && isAmount(row.amount));
  if (!data || textFields.some(key => typeof data[key] !== "string")
      || !Number.isInteger(data.decimal_places) || data.decimal_places! < 0 || data.decimal_places! > 10
      || ![data.gross, data.employee_deductions, data.employer_contributions, data.net].every(isAmount)
      || !(data.taxable === null || isAmount(data.taxable))
      || ![data.earnings, data.deductions, data.employer].every(validLines)) {
    throw new Error("The payslip service returned incomplete data. Update or restart the backend, then try again.");
  }
  return data as Document;
}

export default function PayslipDocument({ path, token }: { path: string; token: string }) {
  const [data, setData] = useState<Document | null>(null); const [error, setError] = useState(""); const [downloading, setDownloading] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => { let active = true; setData(null); setError(""); api<unknown>(path, { token }).then(readDocument).then(result => { if (active) setData(result); }).catch((e: Error) => { if (active) setError(e.message); }); return () => { active = false; }; }, [path, token, revision]);
  async function download() {
    if (!data) return;
    setDownloading(true); setError("");
    try { await apiDownload(`${path}/pdf`, token, data.filename); }
    catch (e) { setError((e as Error).message); } finally { setDownloading(false); }
  }
  const amount = (value: string) => {
    const places = data?.decimal_places ?? 2;
    const negative = value.startsWith("-"); const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
    const separator = new Intl.NumberFormat(undefined).formatToParts(1.1).find(part => part.type === "decimal")?.value || ".";
    return `${negative ? "-" : ""}${BigInt(whole || "0").toLocaleString()}${places ? separator + fraction.padEnd(places, "0").slice(0, places) : ""}`;
  };
  function lines(title: string, number: string, rows: Line[], label: string, total: string) {
    return <section className="payslip-section"><h3><span>{number}</span>{title}</h3><table className="payslip-amounts"><thead><tr><th>Description</th><th>{data?.currency_code}</th></tr></thead><tbody>{rows.length ? rows.map(row => <tr key={row.id}><td>{row.name}</td><td>{amount(row.amount)}</td></tr>) : <tr><td className="payslip-muted">None recorded</td><td>{amount("0")}</td></tr>}</tbody><tfoot><tr><th>{label}</th><td>{amount(total)}</td></tr></tfoot></table></section>;
  }
  return <section className="payslip-preview" aria-label="Payslip preview">
    <div className="payslip-tools"><div><h3>Payslip</h3><p>View your statement or download a PDF copy.</p></div><button className="btn" type="button" disabled={!data || downloading} onClick={() => void download()}>{downloading ? "Preparing PDF…" : "↓ Download PDF"}</button></div>
    {error && <div className="payslip-error" role="alert"><p>{error}</p>{!data && <button type="button" className="btn ghost small" onClick={() => setRevision(v => v + 1)}>Try again</button>}</div>}
    {!data ? !error && <TableSkeleton rows={6} /> : <article className="payslip-paper">
      <header className="payslip-heading"><div className="payslip-brand"><span className="payslip-monogram" aria-hidden="true">{data.company_name.split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]).join("")}</span><div><h2>{data.company_name}</h2>{data.company_legal_name && data.company_legal_name !== data.company_name && <p>{data.company_legal_name}</p>}<p>{[data.company_email, data.company_phone].filter(Boolean).join(" · ")}</p></div></div><div className="payslip-title"><span>PAYSLIP</span><small>{data.reference}</small></div></header>
      {data.status !== "APPROVED" && <p className="payslip-draft">DRAFT — Not approved. For internal review only.</p>}
      <dl className="payslip-details"><div><dt>Employee</dt><dd>{data.employee_name}</dd></div><div><dt>Employee number</dt><dd>{data.employee_number}</dd></div><div><dt>Pay period</dt><dd>{formatDate(data.period_start)} – {formatDate(data.period_end)}</dd></div><div><dt>Branch</dt><dd>{data.branch_name}</dd></div><div><dt>Currency</dt><dd>{data.currency_code}</dd></div><div><dt>PIN number</dt><dd>{data.pin_number ?? ""}</dd></div><div><dt>SHIF no.</dt><dd>{data.shif_no ?? ""}</dd></div><div><dt>NSSF no.</dt><dd>{data.nssf_no ?? ""}</dd></div></dl>
      {lines("Earnings", "01", data.earnings, "Gross pay", data.gross)}
      {lines("Employee deductions", "02", data.deductions, "Total deductions", data.employee_deductions)}
      {data.taxable !== null && <p className="payslip-taxable">Taxable pay<strong>{data.currency_code} {amount(data.taxable)}</strong></p>}
      <section className="payslip-net" aria-label="Net pay"><div><span>NET PAY</span></div><strong><span>{data.currency_code}</span> {amount(data.net)}</strong></section>
      <footer className="payslip-footer"><span>CONFIDENTIAL · Computer-generated payslip</span><span>{data.reference}</span></footer>
    </article>}
  </section>;
}
