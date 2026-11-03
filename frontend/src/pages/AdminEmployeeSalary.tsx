import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { adminToken } from "../api";
import { SalaryBoard } from "./app/EmployeeSalary";

export default function AdminEmployeeSalary() {
  const { tenantId, employeeId } = useParams();
  const navigate = useNavigate();
  const token = adminToken.get();

  useEffect(() => {
    if (!token) navigate("/admin/login", { replace: true });
  }, [token, navigate]);

  if (!token || !tenantId || !employeeId) return null;

  return (
    <SalaryBoard
      token={token}
      apiBase={`/platform/tenants/${tenantId}`}
      employeeId={employeeId}
      canManageHr
      notify={() => undefined}
      peopleHref={`/admin/tenants/${tenantId}?tab=employees`}
      profileHref={(id) => `/admin/tenants/${tenantId}/employees/${id}`}
    />
  );
}
