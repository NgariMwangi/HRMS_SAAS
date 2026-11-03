import { Link } from "react-router-dom";
import { employeeName, type Employee, type Supervisor } from "../types";
import { IconPlus } from "./icons";

export function SupervisorFields({
  people,
  excludeId,
  selectedIds,
  onChange,
}: {
  people: Employee[];
  excludeId?: string;
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const choices = people.filter((row) => row.id !== excludeId);
  const taken = new Set(selectedIds.filter(Boolean));

  function optionsFor(current: string) {
    return choices.filter((row) => row.id === current || !taken.has(row.id));
  }

  return (
    <div className="kin-list">
      <div className="kin-head">
        <div>
          <h3>Supervisors</h3>
          <p>Optional. Pick one or more fellow employees. This person can have none.</p>
        </div>
        <button
          className="btn ghost small"
          type="button"
          disabled={choices.length === 0 || taken.size >= choices.length}
          onClick={() => onChange([...selectedIds, ""])}
        >
          <IconPlus /> Add supervisor
        </button>
      </div>
      {choices.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No other employees in this company yet.</p>
      ) : selectedIds.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No supervisors added.</p>
      ) : (
        selectedIds.map((id, index) => (
          <div className="kin-card" key={`${id}-${index}`}>
            <div className="kin-card-head">
              <strong>Supervisor {index + 1}</strong>
              <button
                className="btn ghost small"
                type="button"
                onClick={() => onChange(selectedIds.filter((_, rowIndex) => rowIndex !== index))}
              >
                Remove
              </button>
            </div>
            <label>
              Employee
              <select
                value={id}
                onChange={(event) => onChange(selectedIds.map((current, rowIndex) => (
                  rowIndex === index ? event.target.value : current
                )))}
              >
                <option value="">Select</option>
                {optionsFor(id).map((row) => (
                  <option key={row.id} value={row.id}>
                    {employeeName(row)} · {row.employee_number}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ))
      )}
    </div>
  );
}

export function SupervisorList({
  rows,
  hrefFor,
}: {
  rows: Supervisor[];
  hrefFor?: (row: Supervisor) => string;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h3>Supervisors</h3>
          <p>Fellow employees this person reports to. Optional.</p>
        </div>
      </div>
      <div className="card-pad">
        {rows.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>No supervisors recorded.</p>
        ) : (
          <div className="kin-list">
            {rows.map((row) => (
              <div className="kin-card" key={row.id}>
                {hrefFor ? (
                  <Link className="row-link" to={hrefFor(row)}>{employeeName(row)}</Link>
                ) : (
                  <strong>{employeeName(row)}</strong>
                )}
                <div className="muted">{row.employee_number}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
