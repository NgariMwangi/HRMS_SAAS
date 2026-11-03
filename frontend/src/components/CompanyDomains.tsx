import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { FormSkeleton, StatusPill } from "../ui";

type Domain = { id: string; hostname: string; kind: "AUTOMATIC" | "CUSTOM"; status: string; dns_records: { type: string; name: string; value: string }[] };

export default function CompanyDomains({ companyId, token, apiBase = "/domains" }: { companyId: string; token: string; apiBase?: string }) {
  const [rows, setRows] = useState<Domain[]>([]);
  const [hostname, setHostname] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const identity = `${apiBase}:${companyId}`;
  const current = useRef(identity); current.current = identity;
  async function load() {
    const data = await api<Domain[]>(`${apiBase}?company_id=${companyId}`, { token });
    if (current.current === identity) setRows(data);
  }
  useEffect(() => {
    let active = true;
    setRows([]); setLoading(true); setError(""); setNotice(""); setHostname("");
    load().catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [identity, token]);
  async function action(path: string, method = "POST", body?: object) {
    setBusy(true); setError(""); setNotice("");
    try {
      await api(path, { token, method, ...(body ? { body: JSON.stringify(body) } : {}) });
      if (current.current === identity) { await load(); setNotice(path.endsWith("/verify") ? "Domain verified. HTTPS is provisioned when the public gateway is running." : "Domain settings saved."); }
    } catch (err) { if (current.current === identity) setError(err instanceof Error ? err.message : "Could not save domain"); }
    finally { setBusy(false); }
  }
  function add(event: FormEvent) { event.preventDefault(); void action(`${apiBase}?company_id=${companyId}`, "POST", { hostname: hostname.trim() }); }
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setNotice("Copied."); }
    catch { setError("Copy is unavailable in this browser. Select and copy the value below."); }
  }
  if (loading) return <section className="card card-pad"><FormSkeleton compact fields={3} /></section>;
  const automatic = rows.find(row => row.kind === "AUTOMATIC");
  return <div className="domain-settings">
    {error && <p className="error" role="alert">{error}</p>}{notice && <p role="status" className="muted">{notice}</p>}
    <section className="card card-pad">
      <h2>Company address</h2><p className="muted">A dedicated sign-in address for this company. Employees and HR use the same address with their usual accounts.</p>
      {automatic ? <div className="domain-address"><a href={`https://${automatic.hostname}`} target="_blank" rel="noreferrer">{automatic.hostname}</a><button className="btn ghost small" onClick={() => void copy(`https://${automatic.hostname}`)}>Copy link</button></div> : <p className="muted">Set the platform main domain to generate a company address.</p>}
      <p className="muted">The address opens publicly after the platform's DNS and HTTPS gateway are connected.</p>
    </section>
    <section className="card card-pad">
      <h2>Connect your own domain</h2><p className="muted">Use an address you own, such as people.yourcompany.com. Add the DNS records with your domain provider, then verify the connection.</p>
      <form onSubmit={add} className="domain-add"><label>Company domain<input required placeholder="people.yourcompany.com" value={hostname} onChange={event => setHostname(event.target.value)} disabled={busy} /></label><button className="btn" disabled={busy || !hostname.trim()}>Add domain</button></form>
    </section>
    {rows.filter(row => row.kind === "CUSTOM").map(row => <section className="card card-pad" key={row.id}>
      <div className="domain-address"><h3>{row.hostname}</h3><StatusPill value={row.status} /></div>
      <p className="muted">{row.status === "ACTIVE" ? "Ownership and routing verified. The gateway issues HTTPS for this address." : row.status === "DISABLED" ? "Disconnected. Verify the DNS records again to reconnect." : "Add both records below. DNS updates may take time to appear."}</p>
      <div className="table-wrap"><table><thead><tr><th>Type</th><th>Name / host</th><th>Value / target</th><th /></tr></thead><tbody>{row.dns_records.map(record => <tr key={record.type}><td>{record.type}</td><td><code>{record.name}</code></td><td><code>{record.value}</code></td><td><button className="btn ghost small" onClick={() => void copy(record.value)}>Copy value</button></td></tr>)}</tbody></table></div>
      <p className="muted">Enter the names as your DNS provider expects them. Keep the TXT record and use a DNS-only CNAME while connecting.</p>
      <div className="domain-actions"><button className="btn" disabled={busy} onClick={() => void action(`${apiBase}/${row.id}/verify`)}>{row.status === "ACTIVE" ? "Check connection" : "Verify connection"}</button>{row.status === "ACTIVE" && <><a className="btn ghost" href={`https://${row.hostname}`} target="_blank" rel="noreferrer">Open portal</a><button className="btn ghost" disabled={busy} onClick={() => { if (window.confirm(`Disconnect ${row.hostname}? Users will need the automatic company address.`)) void action(`${apiBase}/${row.id}/disable`); }}>Disconnect</button></>}<button className="btn ghost" disabled={busy} onClick={() => { if (window.confirm(`Remove ${row.hostname} from this company?`)) void action(`${apiBase}/${row.id}`, "DELETE"); }}>Remove</button></div>
    </section>)}
  </div>;
}
