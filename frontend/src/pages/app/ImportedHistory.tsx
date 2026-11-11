import { useEffect, useState } from "react";
import { api } from "../../api";
import { useWorkspace } from "../../context/WorkspaceContext";

type Table = { table: string; count: number };
type Record = { id: string; source_id: string; destination_table: string | null; destination_ids: string[]; payload: unknown };

export default function ImportedHistory() {
  const { company, user } = useWorkspace();
  const [tables, setTables] = useState<Table[]>([]); const [table, setTable] = useState("");
  const [rows, setRows] = useState<Record[]>([]); const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  useEffect(() => {
    let active = true; setRows([]); setTables([]); setTable(""); setOffset(0);
    if (company && user.role === "OWNER") api<Table[]>(`/legacy-import/tables?company_id=${company.id}`).then(value => { if (active) { setTables(value); setTable(value[0]?.table ?? ""); } }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [company?.id, user.role]);
  useEffect(() => {
    let active = true; setRows([]);
    if (company && table && user.role === "OWNER") {
      setLoading(true); setError("");
      api<Record[]>(`/legacy-import/records?company_id=${company.id}&source_table=${encodeURIComponent(table)}&offset=${offset}`).then(value => { if (active) setRows(value); }).catch((err: Error) => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; };
  }, [company?.id, table, offset, user.role]);
  if (user.role !== "OWNER") return <p>Only the workspace owner can view imported history.</p>;
  const count = tables.find(row => row.table === table)?.count ?? 0;
  return <><div className="page-head"><div><h1>Imported history</h1><p>Original HRMS fields and source references retained during migration. Sensitive credentials are redacted.</p></div></div>
    {error ? <p className="error" role="alert">{error}</p> : null}
    <label>Source records<select value={table} disabled={loading} onChange={event => { setOffset(0); setTable(event.target.value); }}>{tables.map(row => <option key={row.table} value={row.table}>{row.table} ({row.count})</option>)}</select></label>
    {!tables.length ? <p>No imported history is available for this company.</p> : null}
    {loading ? <p>Loading records...</p> : rows.map(row => <details key={row.id} className="card card-pad"><summary>Source #{row.source_id} — {row.destination_table ? `Mapped to ${row.destination_table}` : "Retained original record"}</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(row.payload, null, 2)}</pre></details>)}
    {count ? <div className="actions"><button className="btn" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous records</button><span>{offset + 1}–{Math.min(offset + 25, count)} of {count}</span><button className="btn" disabled={loading || offset + 25 >= count} onClick={() => setOffset(offset + 25)}>Next records</button></div> : null}
  </>;
}
