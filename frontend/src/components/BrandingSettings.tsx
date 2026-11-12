import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { Company } from "../types";
import { brandVariables, CompanyLogo } from "./CompanyBranding";

export default function BrandingSettings({ company, token, canManage, onSaved }: { company: Company; token: string; canManage: boolean; onSaved: () => Promise<void> }) {
  const [color, setColor] = useState(company.theme_color ?? "#4F46E5");
  const [logo, setLogo] = useState(company.logo_data_url ?? null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setColor(company.theme_color ?? "#4F46E5"); setLogo(company.logo_data_url ?? null); setError(""); }, [company]);
  async function upload(file?: File) {
    if (!file) return;
    setError("");
    if (!["image/png", "image/jpeg"].includes(file.type) || file.size > 2 * 1024 * 1024) { setError("Choose a PNG or JPEG logo smaller than 2 MB."); return; }
    setReading(true);
    try {
      const value = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error("Could not read the logo.")); reader.readAsDataURL(file); });
      setLogo(value);
    } catch (err) { setError((err as Error).message); }
    finally { setReading(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!canManage || busy || reading) return;
    setBusy(true); setError("");
    try { await api(`/companies/${company.id}`, { token, method: "PATCH", body: JSON.stringify({ theme_color: color, logo_data_url: logo }) }); await onSaved(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save}>
    <p className="muted">Branding for {company.name}. Used in the workspace, employee portal, payslips, and reports.</p>
    <div className="grid-2">
      <div><label>Theme colour<input type="color" value={color} disabled={!canManage || busy} onChange={event => setColor(event.target.value)} /></label>
        <label>Colour code<input value={color} pattern="#[0-9A-Fa-f]{6}" required readOnly={!canManage} maxLength={7} onChange={event => setColor(event.target.value)} /></label>
        <label>Company logo<input type="file" accept="image/png,image/jpeg" disabled={!canManage || busy || reading} onChange={event => void upload(event.target.files?.[0])} /></label>
        <small className="muted">PNG or JPEG, up to 2 MB. A wide logo works best.</small>
        {canManage && logo && <button type="button" className="btn ghost small" onClick={() => setLogo(null)} disabled={busy || reading}>Remove logo</button>}
      </div>
      <div style={{ ...brandVariables(color), padding: 24, border: "1px solid var(--line)", borderRadius: 12 }}>
        <CompanyLogo company={{ ...company, logo_data_url: logo }} /><h3>{company.name}</h3><p className="muted">Company branding preview</p><button className="btn" type="button">Example button</button>
      </div>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {canManage && <div className="actions" style={{ marginTop: 20 }}><button className="btn" type="submit" disabled={busy || reading}>{busy ? "Saving…" : "Save branding"}</button><button className="btn ghost" type="button" disabled={busy} onClick={() => setColor("#4F46E5")}>Reset colour</button></div>}
  </form>;
}
