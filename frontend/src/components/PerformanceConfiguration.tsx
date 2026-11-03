import { FormEvent, useState } from "react";
import { Card } from "../ui";
import { choices, Values } from "./PerformanceForm";
import type { Level, Scale, Settings } from "./performanceTypes";

export const frequencies = choices("ANNUAL", "SEMI_ANNUAL", "QUARTERLY", "PROBATION", "CUSTOM");

export function SettingsEditor({ settings, scales, save }: { settings: Settings; scales: Scale[]; save: (values: Values) => Promise<void> }) {
  const [config, setConfig] = useState(settings);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const reviewSwitches: Array<[keyof Settings, string]> = [["require_self", "Employee self-review"], ["require_manager", "Manager assessment"], ["require_review", "Review discussion"], ["require_acknowledgement", "Employee acknowledgement"], ["manager_goal_approval", "Manager approval of goals"]];
  const visibility: Array<[keyof Settings, string]> = [["employee_view_manager", "Employees can see manager feedback and scores"], ["employee_view_calibration", "Employees can see confirmed ratings and reasons"]];
  const toggle = ([key, label]: [keyof Settings, string]) => <label key={key}><input type="checkbox" checked={Boolean(config[key])} onChange={event => setConfig(value => ({ ...value, [key]: event.target.checked }))} />{label}</label>;
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await save({ ...config, rating_scale_id: config.rating_scale_id || null, development_threshold: config.development_threshold || null, pip_threshold: config.pip_threshold || null }); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  return <Card title="Review defaults" note="These settings apply to new reviews. Choose goal-entry roles and self-review dates when creating each review." padded><form onSubmit={submit}><fieldset className="performance-fields" disabled={busy}>
    {error && <p className="error" role="alert">{error}</p>}
    <section className="performance-settings-section"><h3>Scoring</h3><p>Decide how goals and competencies contribute to the overall result.</p><div className="form-grid">
      <label>Default review frequency<select value={config.frequency} onChange={event => setConfig(value => ({ ...value, frequency: event.target.value }))}>{frequencies.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label>Rating scale<select value={config.rating_scale_id ?? ""} onChange={event => setConfig(value => ({ ...value, rating_scale_id: event.target.value }))}><option value="">Select rating scale</option>{scales.map(scale => <option key={scale.id} value={scale.id}>{scale.name}</option>)}</select></label>
      {(["kpi_weight", "competency_weight"] as const).map(key => <label key={key}>{key === "kpi_weight" ? "Goals contribution (%)" : "Competencies contribution (%)"}<input type="number" step="0.01" min={0} max={100} required value={config[key] ?? ""} onChange={event => setConfig(value => ({ ...value, [key]: event.target.value }))} /></label>)}
    </div><p className="performance-weight-total">Combined contribution: <strong>{Number(config.kpi_weight) + Number(config.competency_weight)}%</strong> of 100%</p></section>
    <section className="performance-settings-section"><h3>Required review steps</h3><p>Select what must be completed before a review can be closed.</p><div className="performance-switches">{reviewSwitches.map(toggle)}</div></section>
    <section className="performance-settings-section"><h3>Employee visibility</h3><div className="performance-switches">{visibility.map(toggle)}</div></section>
    <details className="performance-extra-filters"><summary>Additional scoring & support settings</summary><div className="performance-switches">{toggle(["require_calibration", "Require HR to confirm ratings before finalization"])}{toggle(["auto_scoring", "Calculate ratings from measurable goal results when no manager rating is provided"])}</div><div className="form-grid">{(["development_threshold", "pip_threshold"] as const).map(key => <label key={key}>{key === "development_threshold" ? "Suggest development support below score" : "Suggest HR improvement review below score"}<input type="number" step="0.01" value={config[key] ?? ""} onChange={event => setConfig(value => ({ ...value, [key]: event.target.value }))} /></label>)}</div><p className="muted">Suggestions help identify support needs. They do not automatically create improvement plans.</p></details>
    <div className="actions"><button className="btn" type="submit">{busy ? "Saving..." : "Save defaults"}</button></div>
  </fieldset></form></Card>;

}

export function ScaleEditor({ scale, save, close }: { scale: Scale | null; save: (values: Values) => Promise<void>; close: () => void }) {
  const [name, setName] = useState(scale?.name ?? "Annual rating scale");
  const [levels, setLevels] = useState<Level[]>(scale?.levels ?? [
    { value: "1", label: "Unsatisfactory", minimum: "1", maximum: "1.99", description: "" }, { value: "2", label: "Needs Improvement", minimum: "2", maximum: "2.99", description: "" }, { value: "3", label: "Meets Expectations", minimum: "3", maximum: "3.99", description: "" }, { value: "4", label: "Exceeds Expectations", minimum: "4", maximum: "4.49", description: "" }, { value: "5", label: "Outstanding", minimum: "4.50", maximum: "5", description: "" },
  ]);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await save({ name, levels }); close(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  return <Card title={scale ? "Edit rating scale" : "Create rating scale"} padded><form onSubmit={submit}><fieldset className="performance-fields" disabled={busy}>{error && <p role="alert" className="error">{error}</p>}<label>Scale name<input required value={name} onChange={event => setName(event.target.value)} /></label>{levels.map((level, index) => <div className="performance-scale-level" key={index}>{(["value", "label", "minimum", "maximum", "description"] as const).map(key => <label key={key}>{{ value: "Rating", label: "Label", minimum: "Score from", maximum: "Score to", description: "Description" }[key]}<input type={["value", "minimum", "maximum"].includes(key) ? "number" : "text"} step="0.01" required={key !== "description"} value={level[key] ?? ""} onChange={event => setLevels(current => current.map((item, position) => position === index ? { ...item, [key]: event.target.value } : item))} /></label>)}<button className="btn danger small" type="button" disabled={levels.length <= 2} onClick={() => setLevels(current => current.filter((_, position) => position !== index))}>Remove</button></div>)}<div className="actions"><button className="btn small" type="button" disabled={levels.length >= 20} onClick={() => setLevels(current => [...current, { value: "", label: "", minimum: "", maximum: "", description: "" }])}>Add rating level</button><button className="btn" type="submit">Save scale</button><button className="btn ghost small" type="button" onClick={close}>Cancel</button></div></fieldset></form></Card>;
}
