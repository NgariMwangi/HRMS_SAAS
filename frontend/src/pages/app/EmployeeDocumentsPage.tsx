import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { EmployeeDocuments } from "../../components/EmployeeDocuments";
import { employeeName, type EmployeeSummary } from "../../types";
import { EmptyState, ProfileSkeleton, StatusPill } from "../../ui";

export default function EmployeeDocumentsPage() {
  const { employeeId } = useParams();
  const { token, company, hasPermission } = useWorkspace();
  const canManageOrg = hasPermission("documents.manage");
  const [employee, setEmployee] = useState<EmployeeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!employeeId) return;
    api<EmployeeSummary>(`/employees/${employeeId}/summary?area=documents`, { token })
      .then((row) => {
        setEmployee(row);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [employeeId, token, company?.id]);

  if (error && !employee) {
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow"><Link to="/app/people">Employees</Link></div>
            <h1>Documents</h1>
          </div>
        </div>
        <section className="card">
          <EmptyState title="Employee not found in this workspace" note={error} />
        </section>
      </>
    );
  }

  if (!employee) {
    return <ProfileSkeleton />;
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <Link to="/app/people">Employees</Link>
            {" / "}
            <Link to={`/app/people/${employee.id}`}>{employeeName(employee)}</Link>
          </div>
          <div className="title-row">
            <h1>Documents</h1>
            <StatusPill value={employee.status} />
          </div>
          <p>{employeeName(employee)} · {employee.employee_number}</p>
        </div>
        <div className="actions">
          <Link className="btn ghost small" to={`/app/people/${employee.id}`}>Back to profile</Link>
        </div>
      </div>
      <EmployeeDocuments
        employeeId={employee.id}
        companyId={employee.company_id}
        token={token}
        apiBase=""
        canManage={canManageOrg}
      />
    </>
  );
}
