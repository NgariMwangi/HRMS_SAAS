import { FormEvent, useState } from "react";

export type Option = { value: string; label: string };
export type Field = { key: string; label: string; type?: "text" | "number" | "date" | "textarea" | "select" | "multi" | "checkbox" | "checks" | "objectives"; options?: Option[]; required?: boolean; disabled?: boolean; min?: number; max?: number; help?: string };
export type Values = Record<string, unknown>;

export function PerformanceForm({ title, fields, initial = {}, submit, close, button = "Save" }: {
  title: string; fields: Field[]; initial?: Values; submit: (values: Values) => Promise<void>; close: () => void; button?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [objectiveCount, setObjectiveCount] = useState(1);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values: Values = {};
    for (const field of fields) {
      if (field.disabled) { values[field.key] = initial[field.key] ?? ""; continue; }
      if (field.type === "checkbox") values[field.key] = data.has(field.key);
      else if (field.type === "multi" || field.type === "checks") {
        values[field.key] = data.getAll(field.key);
        if (field.required && !data.getAll(field.key).length) { setError(`Choose at least one option for ${field.label.toLowerCase()}.`); return; }
      }
      else if (field.type === "objectives") values[field.key] = Array.from({ length: objectiveCount }, (_, index) => ({
        title: String(data.get(`${field.key}.${index}.title`) ?? ""),
        expected_standard: String(data.get(`${field.key}.${index}.expected_standard`) ?? ""),
        target: String(data.get(`${field.key}.${index}.target`) ?? ""),
      }));
      else values[field.key] = String(data.get(field.key) ?? "");
    }
    setBusy(true); setError("");
    try { await submit(values); close(); } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="card performance-form" aria-label={title}>
    <div className="card-head"><h3>{title}</h3><button className="btn ghost small" type="button" onClick={close} disabled={busy}>Close</button></div>
    <form onSubmit={save} className="card-pad">
      {error && <p className="error" role="alert">{error}</p>}
      <fieldset disabled={busy} className="performance-fields"><div className="form-grid">
        {fields.map(field => field.type === "objectives" ? <section className="span-2 performance-objectives" key={field.key}><h4>{field.label}</h4>{Array.from({ length: objectiveCount }, (_, index) => <div className="performance-objective-fields" key={index}><strong>Objective {index + 1}</strong><div className="form-grid"><label>What should improve?<input name={`${field.key}.${index}.title`} required /></label><label>Expected standard<input name={`${field.key}.${index}.expected_standard`} required /></label><label>Measurable target<input name={`${field.key}.${index}.target`} required placeholder="For example: 95% delivered on time" /></label></div></div>)}<div className="actions"><button className="btn ghost small" type="button" onClick={() => setObjectiveCount(count => count + 1)}>Add objective</button>{objectiveCount > 1 && <button className="btn ghost small" type="button" onClick={() => setObjectiveCount(count => count - 1)}>Remove last objective</button>}</div></section> : field.type === "checks" ? <fieldset className="performance-fields span-2" disabled={field.disabled} key={field.key}><legend>{field.label}</legend><div className="performance-form-checks">{field.options?.map(option => <label key={option.value}><input type="checkbox" name={field.key} value={option.value} defaultChecked={(initial[field.key] as string[] ?? []).includes(option.value)} />{option.label}</label>)}</div>{field.help && <small className="muted">{field.help}</small>}</fieldset> : <label key={field.key} className={field.type === "textarea" ? "span-2" : ""}>{field.label}
          {field.type === "textarea" ? <textarea name={field.key} defaultValue={String(initial[field.key] ?? "")} required={field.required} disabled={field.disabled} rows={3} />
            : field.type === "checkbox" ? <input type="checkbox" name={field.key} disabled={field.disabled} defaultChecked={Boolean(initial[field.key])} />
              : field.type === "select" || field.type === "multi" ? <select name={field.key} disabled={field.disabled} multiple={field.type === "multi"} defaultValue={field.type === "multi" ? initial[field.key] as string[] ?? [] : String(initial[field.key] ?? "")} required={field.required}>
                {field.type !== "multi" && <option value="">Select {field.label.toLowerCase()}</option>}
                {field.options?.map(option => <option value={option.value} key={option.value}>{option.label}</option>)}
              </select>
                : <input name={field.key} disabled={field.disabled} type={field.type ?? "text"} defaultValue={String(initial[field.key] ?? "")} required={field.required} min={field.min} max={field.max} step={field.type === "number" ? "any" : undefined} />}
          {field.help && <small>{field.help}</small>}
        </label>)}
      </div><div className="actions"><button className="btn" type="submit">{busy ? "Saving…" : button}</button><button className="btn ghost" type="button" onClick={close}>Cancel</button></div></fieldset>
    </form>
  </section>;
}

export const choices = (...values: string[]): Option[] => values.map(value => ({ value, label: value.replaceAll("_", " ").toLowerCase() }));
export const text = (key: string, label: string, required = false): Field => ({ key, label, type: "textarea", required });
export const dateField = (key: string, label: string, required = false): Field => ({ key, label, type: "date", required });
export const today = () => new Date().toLocaleDateString("en-CA");
export function deadline(due: string) {
  const days = Math.ceil((new Date(`${due}T23:59:59`).getTime() - Date.now()) / 86400000);
  return days < 0 ? `${Math.abs(days)} days overdue` : days === 0 ? "Due today" : `${days} days remaining`;
}
