import { FormEvent, useState } from "react";
import { Card } from "../ui";
export type RecruitmentField = { name: string; label: string; type?: string; required?: boolean; options?: { value: string; label: string }[]; value?: string | number | string[] | null; hint?: string; min?: number; max?: number; step?: string; };
export default function RecruitmentForm({ title, note, fields, submitLabel = "Save", save, cancel }: { title: string; note?: string; fields: RecruitmentField[]; submitLabel?: string; save: (data: Record<string, unknown>) => Promise<void>; cancel: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      const form = new FormData(e.currentTarget); const data: Record<string, unknown> = {};
      for (const f of fields) {
        const value = String(form.get(f.name) ?? "").trim();
        data[f.name] = f.type === "checks" ? form.getAll(f.name) : f.type === "number" ? Number(value) : f.type === "datetime-local" ? new Date(value).toISOString() : value;
        if (f.type === "checks" && !(data[f.name] as string[]).length) throw new Error(`Select at least one ${f.label.toLowerCase()}.`);
      }
      await save(data);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <Card title={title} note={note} padded><form onSubmit={submit} className="recruitment-form"><div className="recruitment-form-fields">{fields.map(f => f.type === "checks" ? <fieldset key={f.name} className="recruitment-panel-options"><legend>{f.label}</legend>{f.options?.map(o => <label key={o.value}><input type="checkbox" name={f.name} value={o.value} defaultChecked={Array.isArray(f.value) && f.value.includes(o.value)} />{o.label}</label>)}{f.hint && <small>{f.hint}</small>}</fieldset> : <label key={f.name} className={f.type === "textarea" ? "recruitment-wide" : ""}>{f.label}{f.required && " *"}
    {f.type === "select" ? <select name={f.name} defaultValue={String(f.value ?? "")} required={f.required}><option value="">{f.required ? "Select…" : "None"}</option>{f.options?.map(o => <option value={o.value} key={o.value}>{o.label}</option>)}</select> : f.type === "textarea" ? <textarea name={f.name} defaultValue={String(f.value ?? "")} required={f.required} rows={4} maxLength={20000} /> : <input name={f.name} type={f.type || "text"} defaultValue={String(f.value ?? "")} required={f.required} min={f.min} max={f.max} step={f.step} maxLength={f.type === "email" ? 254 : 255} />}{f.hint && <small>{f.hint}</small>}</label>)}</div>{error && <div className="error" role="alert">{error}</div>}<div className="actions"><button className="btn" disabled={busy}>{busy ? "Saving…" : submitLabel}</button><button className="btn ghost" type="button" onClick={cancel} disabled={busy}>Cancel</button></div></form></Card>;
}
