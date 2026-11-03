import { useState } from "react";
import GeneralReports from "./GeneralReports";
export default function AdminGeneralReports({ companyId, tenantId, token }: { companyId: string; tenantId: string; token: string }) {
  const [kind, setKind] = useState<string | undefined>();
  return <GeneralReports key={`${companyId}-${kind || "overview"}`} companyId={companyId} token={token} apiBase={`/platform/tenants/${tenantId}`} kind={kind} selectReport={setKind} employeeHref={id => `/admin/tenants/${tenantId}/employees/${id}`} />;
}
