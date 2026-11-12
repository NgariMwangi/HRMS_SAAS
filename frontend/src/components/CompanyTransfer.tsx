import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "../context/WorkspaceContext";
import type { Employee } from "../types";
import { Card } from "../ui";

export default function CompanyTransfer({ employeeId, sourceCompanyId, busy, setBusy }: { employeeId: string; sourceCompanyId: string; busy: boolean; setBusy: (value: boolean) => void }) {
  const { token, companies, allBranches, setCompanyId, setBranchId, notify } = useWorkspace();
  const navigate = useNavigate();
  const [destination, setDestination] = useState("");
  const [branch, setBranch] = useState("");
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Africa/Nairobi" });
  const [effective, setEffective] = useState(today);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const available = companies.filter(row => row.id !== sourceCompanyId && row.status === "ACTIVE");
  const branches = allBranches.filter(row => row.company_id === destination && row.status === "ACTIVE");
  async function transfer(event: FormEvent) {
    event.preventDefault(); if (busy || !destination || !branch) return;
    setBusy(true); setError("");
    try {
      const employee = await api<Employee>(`/employees/${employeeId}/transfer-company`, { token, method: "POST", body: JSON.stringify({ company_id: destination, branch_id: branch, effective_on: effective, note: note.trim() || null }) });
      setCompanyId(employee.company_id); setBranchId(employee.branch_id);
      notify("Company changed. Review the employee’s salary, leave entitlement, role, and supervisors in the new company.");
      navigate(`/app/people/${employee.id}`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  if (!available.length) return null;
  return <Card title="Change company" padded>
    <form onSubmit={transfer}>
      <p>Choose the employee’s new company and branch. Their login, personal information, bank details, photo, and emergency contacts follow the new profile.</p>
      <p className="muted">Payroll, leave, attendance, and documents stay with the old employment record. Set up salary, benefits, deductions, department, role, and supervisors for the new company, and review its leave entitlement. The old profile is closed as part of the transfer.</p>
      <fieldset disabled={busy}><div className="form-grid">
        <label>New company<select required value={destination} onChange={event => { setDestination(event.target.value); setBranch(""); setError(""); }}><option value="">Select company</option>{available.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>New branch<select required value={branch} onChange={event => setBranch(event.target.value)}><option value="">Select branch</option>{branches.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>Transfer date<input type="date" required max={today} value={effective} onChange={event => setEffective(event.target.value)} /></label>
        <label>Note<input maxLength={500} value={note} onChange={event => setNote(event.target.value)} /></label>
      </div><p className="muted">Complete pending leave and overtime reviews first. The transfer date must be after any existing payroll period or approved leave covering this employee.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" className="btn" disabled={busy || !destination || !branch}>{busy ? "Transferring…" : "Transfer employee"}</button></fieldset>
    </form>
  </Card>;
}
