import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { adminToken, api } from "../api";
import type { TenantWorkspace } from "../types";
import { WorkforceBoard } from "./app/WorkforcePayments";

export default function AdminWorkforcePayments() {
  const { tenantId, section } = useParams();
  const token = adminToken.get();
  const [workspace, setWorkspace] = useState<TenantWorkspace | null>(null);
  const [companyId, setCompanyId] = useState("");
  const [notice, setNotice] = useState(""); const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<TenantWorkspace>(`/platform/tenants/${tenantId}/workspace`, { token }).then(row => {
      if (active) { setWorkspace(row); setCompanyId(row.companies[0]?.id ?? ""); }
    }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [tenantId, token]);
  if (!token) return <p>Sign in as a platform administrator.</p>;
  return <><Link to={`/admin/tenants/${tenantId}`}>Back to workspace</Link>{error ? <p className="error">{error}</p> : null}{notice ? <p role="status">{notice}</p> : null}
    <label>Company<select value={companyId} onChange={event => setCompanyId(event.target.value)}>{workspace?.companies.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>
    {workspace && companyId ? <WorkforceBoard key={companyId} token={token} companyId={companyId} branches={workspace.branches.filter(b => b.company_id === companyId)} apiBase={`/platform/tenants/${tenantId}`} hrefBase={`/admin/tenants/${tenantId}/workforce`} page={section} notify={setNotice} /> : null}
  </>;
}
