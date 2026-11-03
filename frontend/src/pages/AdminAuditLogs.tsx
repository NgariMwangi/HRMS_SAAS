import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { adminToken } from "../api";
import { AuditLogs } from "../components/AuditLogs";
import { PageHeader } from "../ui";

export default function AdminAuditLogs() {
  const navigate = useNavigate();
  const token = adminToken.get();

  useEffect(() => {
    if (!token) navigate("/admin/login");
  }, [navigate, token]);

  if (!token) return null;

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every platform and tenant request: who made it, what they asked, and whether it succeeded."
      />
      <section className="card">
        <AuditLogs token={token} path="/platform/audit-logs" />
      </section>
    </>
  );
}
