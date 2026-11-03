import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api, apiUrl } from "../../api";
import { EmployeeBenefits } from "../../components/EmployeeBenefits";
import { EmployeeDeductions } from "../../components/EmployeeDeductions";
import { employeeName, type Compensation, type EmployeeSummary, type PayrollSettings } from "../../types";
import { EmptyState, PageHeader, ProfileSkeleton, formatDate, formatMoney } from "../../ui";

type AllowanceDraft = { name: string; amount: string };

function blankAllowances(): AllowanceDraft[] {
  return [{ name: "", amount: "" }];
}

export type SalaryScope = {
  token: string;
  apiBase?: string;
  employeeId: string;
  canManageHr: boolean;
  notify: (message: string) => void;
  peopleHref: string;
  profileHref: (id: string) => string;
};

export function SalaryBoard({
  token,
  apiBase = "",
  employeeId,
  canManageHr,
  notify,
  peopleHref,
  profileHref,
}: SalaryScope) {
  const [employee, setEmployee] = useState<EmployeeSummary | null>(null);
  const [rows, setRows] = useState<Compensation[]>([]);
  const [settings, setSettings] = useState<PayrollSettings | null>(null);
  const [mode, setMode] = useState<"closed" | "add" | "edit">("closed");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [structure, setStructure] = useState("GROSS_ONLY");
  const [effectiveFrom, setEffectiveFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [gross, setGross] = useState("");
  const [basic, setBasic] = useState("");
  const [allowances, setAllowances] = useState<AllowanceDraft[]>(blankAllowances);
  const [pension, setPension] = useState("");
  const [pensionScheme, setPensionScheme] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(person?: EmployeeSummary) {
    if (!employeeId) return;
    const profile = person ?? (await api<EmployeeSummary>(apiUrl(apiBase, `/employees/${employeeId}${apiBase ? "" : "/summary?area=payroll"}`), { token }));
    setEmployee(profile);
    if (!canManageHr) {
      setRows([]);
      setSettings(null);
      return;
    }
    const [list, config] = await Promise.all([
      api<Compensation[]>(apiUrl(apiBase, `/employees/${profile.id}/compensation`), { token }),
      api<PayrollSettings>(
        apiUrl(apiBase, `/payroll/settings?company_id=${profile.company_id}&branch_id=${profile.branch_id}`),
        { token },
      ),
    ]);
    setRows(list);
    setSettings(config);
  }

  useEffect(() => {
    if (!employeeId) return;
    setLoading(true);
    load()
      .then(() => setError(null))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [employeeId, token, canManageHr, apiBase]);

  function resetForm(nextStructure = settings?.salary_structure ?? "GROSS_ONLY") {
    setStructure(nextStructure);
    setEffectiveFrom(new Date().toISOString().slice(0, 10));
    setGross("");
    setBasic("");
    setAllowances(blankAllowances());
    setPension("");
    setPensionScheme("");
    setEditingId(null);
  }

  function openAdd() {
    resetForm();
    if (rows[0]) {
      setPension(rows[0].voluntary_pension ?? "");
      setPensionScheme(rows[0].pension_scheme ?? "");
    }
    setMode("add");
  }

  function openEdit(row: Compensation) {
    setMode("edit");
    setEditingId(row.id);
    setStructure(row.structure);
    setEffectiveFrom(row.effective_from);
    setGross(row.gross_amount ?? "");
    setBasic(row.basic_amount ?? "");
    setAllowances(
      row.lines.length
        ? row.lines.map((line) => ({ name: line.name, amount: line.amount }))
        : blankAllowances(),
    );
    setPension(row.voluntary_pension ?? "");
    setPensionScheme(row.pension_scheme ?? "");
  }

  function payload() {
    const pensionFields = {
      voluntary_pension: pension || null,
      pension_scheme: pension ? pensionScheme.trim() || null : null,
    };
    if (structure === "GROSS_ONLY") {
      return { effective_from: effectiveFrom, structure, gross_amount: gross, ...pensionFields };
    }
    return {
      effective_from: effectiveFrom,
      structure,
      basic_amount: basic,
      ...pensionFields,
      lines: allowances
        .filter((row) => row.name.trim() && row.amount)
        .map((row, index) => ({ name: row.name.trim(), amount: row.amount, sort_order: index })),
    };
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!employee || !canManageHr) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "edit" && editingId) {
        await api(apiUrl(apiBase, `/employees/${employee.id}/compensation/${editingId}`), {
          method: "PATCH",
          token,
          body: JSON.stringify(payload()),
        });
        notify("Salary corrected.");
      } else {
        await api(apiUrl(apiBase, `/employees/${employee.id}/compensation`), {
          method: "POST",
          token,
          body: JSON.stringify(payload()),
        });
        notify("Salary added.");
      }
      setMode("closed");
      resetForm();
      await load(employee);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save salary");
    } finally {
      setBusy(false);
    }
  }

  if (error && !employee) {
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow"><Link to={peopleHref}>Employees</Link></div>
            <h1>Salary</h1>
          </div>
        </div>
        <section className="card">
          <EmptyState title="Employee not found in this workspace" note={error} />
        </section>
      </>
    );
  }

  if (loading || !employee) {
    return <ProfileSkeleton />;
  }

  const currency = settings?.currency_code;
  const current = rows[0];

  return (
    <>
      <PageHeader
        title="Salary"
        description={`${employeeName(employee)} · ${employee.employee_number}. Add a new amount when pay changes. Edit a row only to correct a mistake.`}
        actions={<Link className="btn ghost small" to={profileHref(employee.id)}>Back to profile</Link>}
      />
      <div className="eyebrow" style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}>
        <Link to={peopleHref}>Employees</Link>
        {" / "}
        <Link to={profileHref(employee.id)}>{employeeName(employee)}</Link>
      </div>
      {error ? <p className="error">{error}</p> : null}

      <section className="card">
        <div className="card-head">
          <div>
            <h3>History</h3>
            <p>
              Current: {current ? `${formatMoney(current.computed_gross, currency)} from ${formatDate(current.effective_from)}` : "none yet"}
              {settings?.currency_code ? ` · ${settings.currency_code}` : ""}
            </p>
          </div>
          {canManageHr ? (
            <button className="btn small" type="button" onClick={openAdd}>Add salary</button>
          ) : null}
        </div>
        {!canManageHr ? (
          <div className="card-pad"><p className="muted" style={{ margin: 0 }}>Salary is managed by HR.</p></div>
        ) : rows.length === 0 && mode === "closed" ? (
          <EmptyState title="No salary yet" note="Add the first amount. Later raises or reductions are new rows with a new effective date." />
        ) : rows.length ? (
          <table className="org-table">
            <thead>
              <tr>
                <th>From</th>
                <th>Structure</th>
                <th>Gross</th>
                <th>Voluntary pension</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.id}>
                  <td data-label="From">
                    {formatDate(row.effective_from)}
                    {index === 0 ? <span className="muted"> · current</span> : null}
                  </td>
                  <td data-label="Structure">{row.structure === "GROSS_ONLY" ? "Gross only" : "Basic + allowances"}</td>
                  <td data-label="Gross">
                    {formatMoney(row.computed_gross, currency)}
                    {row.structure === "BASIC_PLUS_ALLOWANCES" ? (
                      <span className="muted"> · basic {formatMoney(row.computed_basic, currency)}</span>
                    ) : null}
                  </td>
                  <td data-label="Voluntary pension">
                    {row.voluntary_pension ? (
                      <>
                        {formatMoney(row.voluntary_pension, currency)}
                        {row.pension_scheme ? <span className="muted"> · {row.pension_scheme}</span> : null}
                      </>
                    ) : (
                      <span className="muted">None</span>
                    )}
                  </td>
                  <td className="row-actions">
                    <button className="btn ghost small" type="button" onClick={() => openEdit(row)}>Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      {canManageHr && mode !== "closed" ? (
        <section className="card card-pad">
          <h3 style={{ marginTop: 0 }}>{mode === "edit" ? "Correct this salary" : "Add salary"}</h3>
          <p className="muted">
            {mode === "edit"
              ? "Use this when the amount or date was entered wrong. A raise or deduction should be a new salary."
              : "Use a new effective date when pay is increased or reduced."}
          </p>
          <form className="form-grid" onSubmit={save}>
            <label>
              Effective from
              <input type="date" required value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} />
            </label>
            <label>
              Structure
              <select value={structure} onChange={(event) => setStructure(event.target.value)}>
                <option value="GROSS_ONLY">Gross only</option>
                <option value="BASIC_PLUS_ALLOWANCES">Basic + allowances</option>
              </select>
            </label>
            {structure === "GROSS_ONLY" ? (
              <label>
                Gross
                <input type="number" min="1" step="0.01" required value={gross} onChange={(event) => setGross(event.target.value)} />
              </label>
            ) : (
              <>
                <label>
                  Basic
                  <input type="number" min="1" step="0.01" required value={basic} onChange={(event) => setBasic(event.target.value)} />
                </label>
                {allowances.map((row, index) => (
                  <label key={index}>
                    Allowance {index + 1}
                    <span style={{ display: "grid", gridTemplateColumns: "1fr 8rem", gap: "0.5rem" }}>
                      <input
                        placeholder="Name"
                        value={row.name}
                        onChange={(event) => {
                          const next = [...allowances];
                          next[index] = { ...row, name: event.target.value };
                          setAllowances(next);
                        }}
                      />
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="Amount"
                        value={row.amount}
                        onChange={(event) => {
                          const next = [...allowances];
                          next[index] = { ...row, amount: event.target.value };
                          setAllowances(next);
                        }}
                      />
                    </span>
                  </label>
                ))}
                <button className="btn ghost small" type="button" onClick={() => setAllowances((current) => [...current, { name: "", amount: "" }])}>
                  Add allowance
                </button>
              </>
            )}
            <div style={{ gridColumn: "1 / -1" }}>
              <h4 style={{ margin: "0.5rem 0 0.25rem" }}>Voluntary pension</h4>
              <p className="muted" style={{ margin: 0 }}>
                {settings?.country_code === "KE"
                  ? "Monthly employee contribution to a registered pension, provident, or retirement fund. Together with NSSF, up to KES 30,000 (and no more than 30% of gross) comes off taxable pay before PAYE; any excess is deducted after tax."
                  : "Monthly employee contribution to a pension scheme. It is deducted from net pay after tax."}
              </p>
            </div>
            <label>
              Monthly contribution
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={pension}
                onChange={(event) => setPension(event.target.value)}
              />
            </label>
            <label>
              Scheme / provider
              <input
                maxLength={100}
                placeholder="e.g. Britam, ICEA Lion"
                value={pensionScheme}
                disabled={!pension}
                onChange={(event) => setPensionScheme(event.target.value)}
              />
            </label>
            <div className="actions" style={{ gridColumn: "1 / -1" }}>
              <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : mode === "edit" ? "Save correction" : "Save salary"}</button>
              <button className="btn ghost" type="button" onClick={() => { setMode("closed"); resetForm(); }}>Cancel</button>
            </div>
          </form>
        </section>
      ) : null}

      <EmployeeBenefits
        token={token}
        apiBase={apiBase}
        employeeId={employee.id}
        companyId={employee.company_id}
        currency={currency}
        canManage={canManageHr}
        notify={notify}
      />

      <EmployeeDeductions
        token={token}
        apiBase={apiBase}
        employeeId={employee.id}
        companyId={employee.company_id}
        currency={currency}
        canManage={canManageHr}
        notify={notify}
      />
    </>
  );
}

export default function EmployeeSalaryPage() {
  const { employeeId } = useParams();
  const { token, notify, hasPermission } = useWorkspace();
  if (!employeeId) return null;
  return (
    <SalaryBoard
      token={token}
      employeeId={employeeId}
      canManageHr={hasPermission("payroll.manage")}
      notify={notify}
      peopleHref={hasPermission("people.view_all") || hasPermission("people.manage") ? "/app/people" : "/app/payroll"}
      profileHref={(id) => hasPermission("people.view_all") || hasPermission("people.manage") ? `/app/people/${id}` : "/app/payroll"}
    />
  );
}

