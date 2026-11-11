import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, apiUrl } from "../../api";
import { useWorkspace } from "../../context/WorkspaceContext";
import { type Branch } from "../../types";
import { formatDate, formatMoney } from "../../ui";

type Consultant = { id: string; branch_id: string; consultant_number: string; first_name: string; last_name: string; other_names: string | null; email: string | null; phone: string | null; id_number: string | null; pin_number: string | null; bank_name: string | null; bank_branch: string | null; bank_account_number: string | null; bank_code: string | null; start_date: string; end_date: string | null; withholding_rate: string; prorate_payroll: boolean; status: string; notes: string | null };
type Fee = { id: string; effective_from: string; effective_to: string | null; monthly_fee: string; other_allowances: string };
type Pay = { id: string; consultant_id: string; recipient_name: string; gross: string; withholding_tax: string; net: string; payable_days: number; status: string; currency_id: string };
type Overtime = { id: string; employee_name: string; worked_dates: string[]; days: string; daily_rate: string | null; amount: string | null; status: string; review_notes: string | null; currency_id: string };
type Payment = { id: string; recipient_name: string; amount: string; paid_on: string; method: string; reference: string; status: string; currency_id: string; void_reason: string | null };
type Target = { id: string; kind: string; name: string; outstanding: string; currency_id: string };
type Currency = { id: string; code: string; decimal_places: number };
type Person = { id: string; name: string; employee_number: string };
const today = () => new Date().toLocaleDateString("en-CA");
const blank = (branchId = ""): Omit<Consultant, "id"> => ({ branch_id: branchId, consultant_number: "", first_name: "", last_name: "", other_names: null, email: null, phone: null, id_number: null, pin_number: null, bank_name: null, bank_branch: null, bank_account_number: null, bank_code: null, start_date: today(), end_date: null, withholding_rate: "0", prorate_payroll: true, status: "ACTIVE", notes: null });

export function WorkforceBoard({ token, companyId, branches, apiBase = "", hrefBase = "/app/payroll", page = "consultants", notify }: { token: string; companyId: string; branches: Branch[]; apiBase?: string; hrefBase?: string; page?: string; notify: (message: string) => void }) {
  const [month, setMonth] = useState(today().slice(0, 7));
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [pays, setPays] = useState<Pay[]>([]);
  const [overtime, setOvertime] = useState<Overtime[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState(blank());
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState("");
  const [fees, setFees] = useState<Fee[]>([]);
  const [feeForm, setFeeForm] = useState({ effective_from: today(), effective_to: "", monthly_fee: "", other_allowances: "0" });
  const [otForm, setOtForm] = useState({ employee_id: "", worked_dates: "", days: "1", daily_rate: "", reason: "" });
  const [reviewNote, setReviewNote] = useState("");
  const [paymentForm, setPaymentForm] = useState({ target: "", amount: "", paid_on: today(), method: "BANK", reference: "", note: "" });
  const [voidId, setVoidId] = useState(""); const [voidReason, setVoidReason] = useState("");
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const version = useRef(0);
  const path = (value: string) => apiUrl(apiBase, `/workforce${value}`);
  const query = `company_id=${companyId}&month=${month}-01`;
  const money = (amount: string, currencyId: string) => { const currency = currencies.find(c => c.id === currencyId); return formatMoney(amount, currency?.code ?? ""); };
  async function load() {
    if (!companyId || !branches.length) { setLoading(false); return; }
    const current = ++version.current;
    setLoading(true);
    try {
      const [c, p, o, ledger, t, currencyRows, employees] = await Promise.all([
        api<Consultant[]>(path(`/consultants?company_id=${companyId}`), { token }), api<Pay[]>(path(`/consultant-pay?${query}`), { token }),
        api<Overtime[]>(path(`/overtime?${query}`), { token }), api<Payment[]>(path(`/payments?${query}`), { token }),
        api<Target[]>(path(`/payment-targets?${query}`), { token }), api<Currency[]>(path("/currencies"), { token }),
        api<Person[]>(apiUrl(apiBase, `/payroll/employees?company_id=${companyId}&branch_id=${branches[0]?.id ?? ""}`), { token }).then(async first => {
          const rest = await Promise.all(branches.slice(1).map(branch => api<Person[]>(apiUrl(apiBase, `/payroll/employees?company_id=${companyId}&branch_id=${branch.id}`), { token })));
          return [...first, ...rest.flat()];
        }),
      ]);
      if (current === version.current) { setConsultants(c); setPays(p); setOvertime(o); setPayments(ledger); setTargets(t); setCurrencies(currencyRows); setPeople(employees); }
    } catch (err) { if (current === version.current) setError((err as Error).message); }
    finally { if (current === version.current) setLoading(false); }
  }
  useEffect(() => { setError(null); setSelected(""); setShowForm(false); setPaymentForm({ target: "", amount: "", paid_on: today(), method: "BANK", reference: "", note: "" }); void load(); return () => { version.current++; }; }, [companyId, month, token, apiBase]);
  useEffect(() => { let active = true; setFees([]); if (selected) api<Fee[]>(path(`/consultants/${selected}/fees`), { token }).then(rows => { if (active) setFees(rows); }).catch((err: Error) => { if (active) setError(err.message); }); return () => { active = false; }; }, [selected, token, apiBase]);
  async function action(work: () => Promise<unknown>, message: string) {
    setBusy(true); setError(null);
    try { await work(); notify(message); await load(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  function send(endpoint: string, body: unknown, method = "POST") { return api(path(endpoint), { token, method, body: JSON.stringify(body) }); }
  async function saveConsultant(event: FormEvent) {
    event.preventDefault(); await action(async () => { await send(`/consultants${editing ? `/${editing}` : ""}`, editing ? form : { ...form, company_id: companyId }, editing ? "PUT" : "POST"); setShowForm(false); }, "Consultant saved.");
  }
  async function saveFee(event: FormEvent) {
    event.preventDefault(); await action(async () => { await send(`/consultants/${selected}/fees`, { ...feeForm, effective_to: feeForm.effective_to || null }); setFees(await api<Fee[]>(path(`/consultants/${selected}/fees`), { token })); }, "Consultant fee saved.");
  }
  const selectedTarget = targets.find(t => `${t.kind}:${t.id}` === paymentForm.target);
  if (!companyId || !branches.length) return <p>Select a company with a branch.</p>;
  return <>
    <div className="page-head"><div><h1>{page === "overtime" ? "Overtime" : page === "payments" ? "Payment history" : "Consultants"}</h1><p>Consultant pay, overtime approvals and recorded payments.</p></div></div>
    <nav className="tabs">{["consultants", "overtime", "payments"].map(tab => <Link key={tab} className={page === tab ? "active" : ""} to={`${hrefBase}/${tab}`}>{tab === "payments" ? "Payment history" : tab[0].toUpperCase() + tab.slice(1)}</Link>)}</nav>
    <label>Payroll month<input type="month" required value={month} disabled={busy} onChange={event => { if (event.target.value) setMonth(event.target.value); }} /></label>
    {error ? <p className="error" role="alert">{error}</p> : null}
    {loading ? <p>Loading records...</p> : null}
    <fieldset disabled={busy || loading} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
    {page === "consultants" ? <>
      <section className="card"><div className="card-head"><h3>Consultants</h3><button className="btn primary" onClick={() => { setEditing(null); setForm(blank(branches[0]?.id)); setShowForm(true); }}>Add consultant</button></div>
      <div className="table-wrap"><table><thead><tr><th>Name / number</th><th>Branch</th><th>Status</th><th>Actions</th></tr></thead><tbody>{consultants.map(person => <tr key={person.id}><td>{person.first_name} {person.last_name}<div className="muted">{person.consultant_number}</div></td><td>{branches.find(b => b.id === person.branch_id)?.name}</td><td>{person.status}</td><td><button className="btn small" onClick={() => { const { id, ...draft } = person; setEditing(id); setForm(draft); setShowForm(true); }}>Edit</button> <button className="btn small" onClick={() => setSelected(person.id)}>Fees</button> <button className="btn small" onClick={() => action(() => send(`/consultants/${person.id}/calculate`, { month: `${month}-01` }), "Consultant pay calculated.")} disabled={person.status !== "ACTIVE"}>Calculate month</button></td></tr>)}</tbody></table>{!consultants.length ? <p className="card-pad">No consultants yet.</p> : null}</div></section>
      {showForm ? <section className="card card-pad"><h3>{editing ? "Edit consultant" : "New consultant"}</h3><form onSubmit={saveConsultant}><div className="form-grid">
        <label>Branch<select required value={form.branch_id} onChange={event => setForm({ ...form, branch_id: event.target.value })}>{branches.map(branch => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></label>
        {([['consultant_number', 'Consultant number'], ['first_name', 'First name'], ['last_name', 'Last name'], ['other_names', 'Other names'], ['email', 'Work email'], ['phone', 'Phone'], ['id_number', 'ID number'], ['pin_number', 'PIN number'], ['bank_name', 'Bank name'], ['bank_branch', 'Bank branch'], ['bank_account_number', 'Account number'], ['bank_code', 'Bank code']] as const).map(([key, label]) => <label key={key}>{label}<input type={key === "email" ? "email" : "text"} required={["consultant_number", "first_name", "last_name"].includes(key)} value={form[key] ?? ""} onChange={event => setForm({ ...form, [key]: event.target.value || null })} /></label>)}
        <label>Start date<input type="date" required value={form.start_date} onChange={event => setForm({ ...form, start_date: event.target.value })} /></label>
        <label>End date<input type="date" min={form.start_date} value={form.end_date ?? ""} onChange={event => setForm({ ...form, end_date: event.target.value || null })} /></label>
        <label>Withholding rate (%)<input type="number" min="0" max="100" step="0.001" required value={form.withholding_rate} onChange={event => setForm({ ...form, withholding_rate: event.target.value })} /></label>
        <label>Status<select value={form.status} onChange={event => setForm({ ...form, status: event.target.value })}><option>ACTIVE</option><option>INACTIVE</option></select></label>
        <label>Notes<textarea value={form.notes ?? ""} onChange={event => setForm({ ...form, notes: event.target.value || null })} /></label>
      </div><label><input type="checkbox" checked={form.prorate_payroll} onChange={event => setForm({ ...form, prorate_payroll: event.target.checked })} /> Prorate consultant fees for partial months</label><p className="muted">Enter the agreed withholding rate. The system does not select a rate for you.</p><button className="btn primary">Save consultant</button> <button type="button" className="btn" onClick={() => setShowForm(false)}>Cancel</button></form></section> : null}
      {selected ? <section className="card card-pad"><h3>Fee history — {consultants.find(c => c.id === selected)?.first_name}</h3><p>Amounts use the consultant branch currency. A new effective date preserves previous rates.</p>
        {fees.map(fee => <p key={fee.id}>{formatDate(fee.effective_from)}{fee.effective_to ? ` to ${formatDate(fee.effective_to)}` : " onwards"}: monthly fee {fee.monthly_fee}, allowances {fee.other_allowances}</p>)}
        <form onSubmit={saveFee}><div className="form-grid"><label>Effective from<input type="date" required value={feeForm.effective_from} onChange={event => setFeeForm({ ...feeForm, effective_from: event.target.value })} /></label><label>Effective to (optional)<input type="date" min={feeForm.effective_from} value={feeForm.effective_to} onChange={event => setFeeForm({ ...feeForm, effective_to: event.target.value })} /></label><label>Monthly fee<input type="number" min="0.01" step="0.01" required value={feeForm.monthly_fee} onChange={event => setFeeForm({ ...feeForm, monthly_fee: event.target.value })} /></label><label>Other allowances<input type="number" min="0" step="0.01" required value={feeForm.other_allowances} onChange={event => setFeeForm({ ...feeForm, other_allowances: event.target.value })} /></label></div><button className="btn primary">Add fee</button></form></section> : null}
      <section className="card"><div className="card-head"><h3>Consultant pay for {month}</h3></div><div className="table-wrap"><table><thead><tr><th>Consultant</th><th>Days / 30</th><th>Gross</th><th>Withholding</th><th>Net</th><th>Status</th><th /></tr></thead><tbody>{pays.map(pay => <tr key={pay.id}><td>{pay.recipient_name}</td><td>{pay.payable_days}</td><td>{money(pay.gross, pay.currency_id)}</td><td>{money(pay.withholding_tax, pay.currency_id)}</td><td>{money(pay.net, pay.currency_id)}</td><td>{pay.status}</td><td>{pay.status === "DRAFT" ? <button className="btn small" onClick={() => action(() => send(`/consultant-pay/${pay.id}/approve`, {}), "Consultant pay approved.")}>Approve</button> : <Link to={`${hrefBase}/payments`}>Record payment</Link>}</td></tr>)}</tbody></table>{!pays.length ? <p className="card-pad">No consultant pay calculated for this month.</p> : null}</div></section>
    </> : null}
    {page === "overtime" ? <>
      <section className="card card-pad"><h3>Add overtime</h3><p>Enter the agreed daily rate in the employee branch currency. Approval adds a one-off earning to the selected payroll month. Rerun a draft payroll to include it.</p>
      <form onSubmit={event => { event.preventDefault(); void action(async () => { await send("/overtime", { ...otForm, month: `${month}-01`, worked_dates: otForm.worked_dates.split(",").map(s => s.trim()).filter(Boolean) }); setOtForm({ employee_id: "", worked_dates: "", days: "1", daily_rate: "", reason: "" }); }, "Overtime request saved."); }}><div className="form-grid">
        <label>Employee<select required value={otForm.employee_id} onChange={event => setOtForm({ ...otForm, employee_id: event.target.value })}><option value="">Select employee</option>{people.map(person => <option key={person.id} value={person.id}>{person.name} / {person.employee_number}</option>)}</select></label>
        <label>Worked dates (YYYY-MM-DD, separated by commas)<input required placeholder="2026-11-07, 2026-11-08" value={otForm.worked_dates} onChange={event => setOtForm({ ...otForm, worked_dates: event.target.value })} /></label>
        <label>Overtime days<input type="number" min="0.0001" max="31" step="0.0001" required value={otForm.days} onChange={event => setOtForm({ ...otForm, days: event.target.value })} /></label><label>Daily rate<input type="number" min="0.01" step="0.01" required value={otForm.daily_rate} onChange={event => setOtForm({ ...otForm, daily_rate: event.target.value })} /></label><label>Reason<textarea value={otForm.reason} onChange={event => setOtForm({ ...otForm, reason: event.target.value })} /></label></div><button className="btn primary">Save overtime request</button></form></section>
      <section className="card card-pad"><h3>Overtime for {month}</h3><label>Review note<textarea value={reviewNote} onChange={event => setReviewNote(event.target.value)} /></label><div className="table-wrap"><table><thead><tr><th>Employee</th><th>Worked dates</th><th>Days × rate</th><th>Amount</th><th>Status / note</th><th>Review</th></tr></thead><tbody>{overtime.map(row => <tr key={row.id}><td>{row.employee_name}</td><td>{row.worked_dates.join(", ")}</td><td>{row.days} × {row.daily_rate}</td><td>{row.amount === null ? "Not recorded" : money(row.amount, row.currency_id)}</td><td>{row.status}<div>{row.review_notes}</div></td><td>{row.status === "PENDING" ? ["APPROVED", "REJECTED", "CANCELLED"].map(decision => <button key={decision} className="btn small" onClick={() => action(() => send(`/overtime/${row.id}/review`, { decision, note: reviewNote || null }), "Overtime reviewed.")}>{decision === "APPROVED" ? "Approve" : decision === "REJECTED" ? "Decline" : "Cancel"}</button>) : null}</td></tr>)}</tbody></table>{!overtime.length ? <p>No overtime requests for this month.</p> : null}</div></section>
    </> : null}
    {page === "payments" ? <>
      <section className="card card-pad"><h3>Record a payment</h3><p>Record a payment already made. Approved payroll and consultant pay allow partial payments. Benefits paid outside payroll must be settled in full. Payroll still taxes the earning and subtracts the amount already paid.</p>
      <form onSubmit={event => { event.preventDefault(); if (!selectedTarget) return; void action(async () => { await send("/payments", { ...paymentForm, kind: selectedTarget.kind, target_id: selectedTarget.id, month: `${month}-01` }); setPaymentForm({ target: "", amount: "", paid_on: today(), method: "BANK", reference: "", note: "" }); }, "Payment recorded."); }}><div className="form-grid">
        <label>Payable record<select required value={paymentForm.target} onChange={event => { const target = targets.find(t => `${t.kind}:${t.id}` === event.target.value); setPaymentForm({ ...paymentForm, target: event.target.value, amount: target?.outstanding ?? "" }); }}><option value="">Select a record</option>{targets.filter(t => Number(t.outstanding) > 0).map(target => <option key={`${target.kind}:${target.id}`} value={`${target.kind}:${target.id}`}>{target.kind} — {target.name} — {money(target.outstanding, target.currency_id)} outstanding</option>)}</select></label>
        <label>Amount{selectedTarget ? ` (${currencies.find(c => c.id === selectedTarget.currency_id)?.code ?? ""})` : ""}<input type="number" min="0.01" step="0.01" required value={paymentForm.amount} onChange={event => setPaymentForm({ ...paymentForm, amount: event.target.value })} /></label><label>Paid on<input type="date" required value={paymentForm.paid_on} onChange={event => setPaymentForm({ ...paymentForm, paid_on: event.target.value })} /></label><label>Method<select value={paymentForm.method} onChange={event => setPaymentForm({ ...paymentForm, method: event.target.value })}>{["BANK", "MPESA", "CASH", "OTHER"].map(method => <option key={method}>{method}</option>)}</select></label><label>Unique payment reference<input required maxLength={100} value={paymentForm.reference} onChange={event => setPaymentForm({ ...paymentForm, reference: event.target.value })} /></label><label>Note<textarea value={paymentForm.note} onChange={event => setPaymentForm({ ...paymentForm, note: event.target.value })} /></label></div><button className="btn primary">Record payment</button></form></section>
      <section className="card card-pad"><h3>Payment history for payroll month {month}</h3><div className="table-wrap"><table><thead><tr><th>Recipient</th><th>Paid on</th><th>Amount</th><th>Method / reference</th><th>Status</th><th /></tr></thead><tbody>{payments.map(payment => <tr key={payment.id}><td>{payment.recipient_name}</td><td>{formatDate(payment.paid_on)}</td><td>{money(payment.amount, payment.currency_id)}</td><td>{payment.method}<div>{payment.reference}</div></td><td>{payment.status}<div>{payment.void_reason}</div></td><td>{payment.status === "POSTED" ? <button className="btn small" onClick={() => { setVoidId(payment.id); setVoidReason(""); }}>Void</button> : null}</td></tr>)}</tbody></table>{!payments.length ? <p>No payments recorded for this payroll month.</p> : null}</div>
      {voidId ? <form onSubmit={event => { event.preventDefault(); void action(async () => { await send(`/payments/${voidId}/void`, { reason: voidReason }); setVoidId(""); }, "Payment voided. History was retained."); }}><label>Reason for voiding<input required value={voidReason} onChange={event => setVoidReason(event.target.value)} /></label><button className="btn primary">Confirm void</button> <button type="button" className="btn" onClick={() => setVoidId("")}>Cancel</button></form> : null}</section>
    </> : null}
    </fieldset>
  </>;
}

export default function WorkforcePayments() {
  const { section } = useParams();
  const { token, company, branches, notify, hasPermission } = useWorkspace();
  if (!hasPermission("payroll.manage")) return <p>You do not have permission to manage payroll.</p>;
  return <WorkforceBoard key={company?.id} token={token} companyId={company?.id ?? ""} branches={branches} page={section} notify={notify} />;
}
