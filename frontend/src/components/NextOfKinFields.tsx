import { emptyNextOfKin, NEXT_OF_KIN_RELATIONSHIPS, type NextOfKin, type NextOfKinDraft } from "../types";
import { IconPlus } from "./icons";

export function NextOfKinFields({
  rows,
  onChange,
}: {
  rows: NextOfKinDraft[];
  onChange: (rows: NextOfKinDraft[]) => void;
}) {
  function update(index: number, field: keyof NextOfKinDraft, value: string) {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)));
  }

  return (
    <div className="kin-list">
      <div className="kin-head">
        <div>
          <h3>Next of kin</h3>
          <p>Optional. Add one or more people to contact. A row can be removed at any time.</p>
        </div>
        <button
          className="btn ghost small"
          type="button"
          onClick={() => onChange([...rows, emptyNextOfKin()])}
        >
          <IconPlus /> Add next of kin
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No next of kin added.</p>
      ) : null}
      {rows.map((row, index) => (
        <div className="kin-card" key={index}>
          <div className="kin-card-head">
            <strong>Next of kin {index + 1}</strong>
            <button
              className="btn ghost small"
              type="button"
              onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
            >
              Remove
            </button>
          </div>
          <div className="form-grid">
            <label>
              Full name
              <input value={row.name} onChange={(event) => update(index, "name", event.target.value)} />
            </label>
            <label>
              Relationship
              <select value={row.relationship} onChange={(event) => update(index, "relationship", event.target.value)}>
                <option value="">Select</option>
                {NEXT_OF_KIN_RELATIONSHIPS.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Phone
              <input value={row.phone} onChange={(event) => update(index, "phone", event.target.value)} />
            </label>
            <label>
              Second phone
              <input value={row.other_phone} onChange={(event) => update(index, "other_phone", event.target.value)} />
            </label>
            <label>
              Email
              <input type="email" value={row.email} onChange={(event) => update(index, "email", event.target.value)} />
            </label>
            <label>
              Address
              <input value={row.address} onChange={(event) => update(index, "address", event.target.value)} />
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}

export function NextOfKinList({ rows }: { rows: NextOfKin[] }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h3>Next of kin</h3>
          <p>People to contact. This section is optional.</p>
        </div>
      </div>
      <div className="card-pad">
        {rows.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>No next of kin recorded.</p>
        ) : (
          <div className="kin-list">
            {rows.map((row) => (
              <div className="kin-card" key={row.id}>
                <strong>{row.name}</strong>
                <dl className="meta-grid">
                  <div><dt>Relationship</dt><dd>{row.relationship}</dd></div>
                  <div><dt>Phone</dt><dd>{row.phone}</dd></div>
                  {row.other_phone ? <div><dt>Second phone</dt><dd>{row.other_phone}</dd></div> : null}
                  {row.email ? <div><dt>Email</dt><dd>{row.email}</dd></div> : null}
                  {row.address ? <div><dt>Address</dt><dd>{row.address}</dd></div> : null}
                </dl>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
