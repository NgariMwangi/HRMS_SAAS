import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
import { api, apiUrl } from "../api";
import { formatLeaveDays, type LeavePerson, type LeaveBalance, type LeaveType } from "../types";
import { EmptyState, SearchField, matchesSearch } from "../ui";

function usePhoneList() {
  const [phone, setPhone] = useState(() => window.matchMedia("(max-width: 800px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 800px)");
    const sync = () => setPhone(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return phone;
}

export function LeaveBalances({
  token,
  apiBase = "",
  companyId,
  employees,
  types,
  canManageHr,
  employeeId,
}: {
  token: string;
  apiBase?: string;
  companyId: string;
  employees: LeavePerson[];
  types: LeaveType[];
  canManageHr: boolean;
  employeeId?: string;
}) {
  const phoneList = usePhoneList();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [typeId, setTypeId] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<LeaveBalance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<LeaveBalance | null>(null);
  const [extra, setExtra] = useState("0");
  const [busy, setBusy] = useState(false);

  const years = [thisYear - 1, thisYear, thisYear + 1];

  async function load() {
    const params = new URLSearchParams({ company_id: companyId, year: String(year) });
    if (employeeId) params.set("employee_id", employeeId);
    if (typeId) params.set("leave_type_id", typeId);
    const list = await api<LeaveBalance[]>(apiUrl(apiBase, `/leave-balances?${params}`), { token });
    setRows(list);
  }

  useEffect(() => {
    setLoading(true);
    load()
      .then(() => setError(null))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [companyId, employeeId, typeId, year, token, apiBase]);

  const visible = useMemo(
    () => rows.filter((row) => matchesSearch(query, row.employee_name, row.employee_number, row.leave_type_name)),
    [rows, query],
  );

  function openAdjust(row: LeaveBalance) {
    setEditing(row);
    setExtra(String(Number(row.extra)));
    setError(null);
  }

  function closeAdjust() {
    setEditing(null);
    setExtra("0");
  }

  async function saveAdjust(event: FormEvent) {
    event.preventDefault();
    if (!canManageHr || !editing) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<LeaveBalance>(apiUrl(apiBase, "/leave-balances"), {
        method: "PATCH",
        token,
        body: JSON.stringify({
          employee_id: editing.employee_id,
          leave_type_id: editing.leave_type_id,
          year: editing.year,
          extra_days: Number(extra || 0),
        }),
      });
      setRows((current) =>
        current.map((row) =>
          row.employee_id === saved.employee_id && row.leave_type_id === saved.leave_type_id && row.year === saved.year
            ? saved
            : row,
        ),
      );
      closeAdjust();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the balance");
    } finally {
      setBusy(false);
    }
  }

  const form = editing ? (
    <form onSubmit={saveAdjust}>
      <h3 style={{ fontSize: "1rem", margin: 0 }}>Adjust extra days</h3>
      <p className="muted" style={{ margin: "0.35rem 0 0" }}>
        {editing.employee_name} · {editing.leave_type_name} · {editing.year}
      </p>
      <div className="form-grid" style={{ marginTop: "0.75rem" }}>
        <label>Extra days<input required type="number" step="0.5" value={extra} onChange={(event) => setExtra(event.target.value)} /></label>
      </div>
      <div className="actions" style={{ marginTop: 12 }}>
        <button className="btn ghost" type="button" onClick={closeAdjust}>Cancel</button>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </form>
  ) : null;

  return (
    <div className="titles-page">
      <div className="card-head">
        <div>
          <h3>Leave balances</h3>
          <p>Yearly entitlement minus approved and pending leave. Accrued types earn from the join date. Extra days are HR adjustments.</p>
        </div>
      </div>
      <div className="card-pad" style={{ display: "grid", gap: "0.75rem" }}>
        <div className="form-grid">
          <label>Year
            <select value={year} onChange={(event) => setYear(Number(event.target.value))}>
              {years.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          {employeeId ? null : (
            <label>Leave type
              <select value={typeId} onChange={(event) => setTypeId(event.target.value)}>
                <option value="">All types</option>
                {types.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        {employeeId ? null : <SearchField value={query} onChange={setQuery} placeholder="Search employee or type" />}
      </div>
      {error ? <p className="error" style={{ margin: "0 1.1rem" }}>{error}</p> : null}
      {loading ? (
        <p className="muted card-pad">Loading balances…</p>
      ) : visible.length === 0 ? (
        <EmptyState title="No leave balances" note={employees.length === 0 || types.length === 0 ? "Add employees and leave types first." : "Nothing matches these filters."} />
      ) : (
        <>
          <table className="titles-table">
            <thead>
              <tr>
                {employeeId ? null : <th>Employee</th>}
                <th>Type</th>
                <th>Entitled</th>
                <th>Extra</th>
                <th>Used</th>
                <th>Pending</th>
                <th>Remaining</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <Fragment key={`${row.employee_id}-${row.leave_type_id}-${row.year}`}>
                  <tr className={editing?.employee_id === row.employee_id && editing.leave_type_id === row.leave_type_id ? "is-active" : ""}>
                    {employeeId ? null : <td>{row.employee_name}<div className="muted">{row.employee_number}</div></td>}
                    <td>{row.leave_type_name}{row.accrued ? <div className="muted">Accrued</div> : null}</td>
                    <td>{formatLeaveDays(row.entitled, row.unlimited)}</td>
                    <td>{formatLeaveDays(row.extra)}</td>
                    <td>{formatLeaveDays(row.used)}</td>
                    <td>{formatLeaveDays(row.pending)}</td>
                    <td>{formatLeaveDays(row.remaining, row.unlimited)}</td>
                    <td>
                      {canManageHr ? (
                        <button className="btn ghost small" type="button" onClick={() => openAdjust(row)}>Adjust</button>
                      ) : null}
                    </td>
                  </tr>
                  {editing && editing.employee_id === row.employee_id && editing.leave_type_id === row.leave_type_id && !phoneList ? (
                    <tr className="titles-inline-form"><td colSpan={employeeId ? 7 : 8}>{form}</td></tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
          <ul className="titles-list">
            {visible.map((row) => (
              <Fragment key={`${row.employee_id}-${row.leave_type_id}-${row.year}`}>
                <li className={editing?.employee_id === row.employee_id && editing.leave_type_id === row.leave_type_id ? "titles-row is-active" : "titles-row"}>
                  <div className="titles-row-top">
                    <div className="titles-main">
                      <strong>{employeeId ? row.leave_type_name : row.employee_name}</strong>
                      <span>
                        {employeeId ? null : `${row.leave_type_name} · `}
                        Remaining {formatLeaveDays(row.remaining, row.unlimited)}
                        {row.accrued ? " · Accrued" : ""}
                      </span>
                    </div>
                  </div>
                  <div className="muted">
                    Entitled {formatLeaveDays(row.entitled, row.unlimited)} · Extra {formatLeaveDays(row.extra)} · Used {formatLeaveDays(row.used)} · Pending {formatLeaveDays(row.pending)}
                  </div>
                  {canManageHr ? (
                    <div className="row-actions">
                      <button className="btn ghost small" type="button" onClick={() => openAdjust(row)}>Adjust</button>
                    </div>
                  ) : null}
                </li>
                {editing && editing.employee_id === row.employee_id && editing.leave_type_id === row.leave_type_id && phoneList ? (
                  <li className="titles-inline-form">{form}</li>
                ) : null}
              </Fragment>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
