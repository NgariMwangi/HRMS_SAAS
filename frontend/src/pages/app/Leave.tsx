import { useEffect, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { LeaveBalances } from "../../components/LeaveBalances";
import { LeaveRequests } from "../../components/LeaveRequests";
import { LeaveTypes } from "../../components/LeaveTypes";
import { PublicHolidays } from "../../components/PublicHolidays";
import type { LeavePerson, LeaveType, PublicHoliday } from "../../types";
import { FormSkeleton, PageHeader } from "../../ui";

export default function LeavePage() {
  const { token, user, company, branch, notify, hasPermission } = useWorkspace();
  const canManageOrg = hasPermission("leave.manage");
  const [section, setSection] = useState<"Requests" | "Balances" | "Types" | "Holidays">("Requests");
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [holidays, setHolidays] = useState<PublicHoliday[]>([]);
  const [employees, setEmployees] = useState<LeavePerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const canManageHr = hasPermission("leave.manage");

  useEffect(() => {
    if (!company || !token) {
      setTypes([]);
      setHolidays([]);
      setEmployees([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([
      api<LeaveType[]>(`/leave-types?company_id=${company.id}`, { token }),
      api<PublicHoliday[]>(
        `/public-holidays?company_id=${company.id}${branch ? `&branch_id=${branch.id}` : ""}`,
        { token },
      ),
      api<LeavePerson[]>(`/leave-requests/people?company_id=${company.id}`, { token }),
    ])
      .then(([typeRows, holidayRows, people]) => {
        setTypes(typeRows);
        setHolidays(holidayRows);
        setEmployees(people);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [company?.id, branch?.id, token]);

  return (
    <>
      <PageHeader
        title="Leave"
        description={`Requests, balances, types, and public holidays for ${company?.name ?? "this company"}.`}
      />
      <div className="page-tabs">
        {(["Requests", "Balances", "Types", "Holidays"] as const).map((item) => (
          <button key={item} type="button" className={section === item ? "active" : ""} onClick={() => setSection(item)}>
            {item}
          </button>
        ))}
      </div>
      {error ? <p className="error">{error}</p> : null}
      {section === "Requests" ? (
        <section className="card">
          {!company || loading ? (
            <div className="card-pad"><FormSkeleton compact fields={4} /></div>
          ) : (
            <LeaveRequests
              token={token}
              companyId={company.id}
              employees={employees}
              types={types}
              canManageHr={canManageHr}
              selfEmployeeId={hasPermission("leave.view_own") && employees.some((row) => row.id === user.employee_id) ? user.employee_id : null}
              canManageTeam={hasPermission("leave.view_team")}
              supervisorEmployeeId={user.employee_id}
              notify={notify}
            />
          )}
        </section>
      ) : section === "Balances" ? (
        <section className="card">
          {!company || loading ? (
            <div className="card-pad"><FormSkeleton compact fields={4} /></div>
          ) : (
            <LeaveBalances
              token={token}
              companyId={company.id}
              employees={employees}
              types={types}
              canManageHr={canManageHr}
            />
          )}
        </section>
      ) : section === "Types" ? (
        <section className="card">
          {!company || loading ? (
            <div className="card-pad"><FormSkeleton compact fields={4} /></div>
          ) : (
            <LeaveTypes
              token={token}
              apiBase=""
              companyId={company.id}
              rows={types}
              canManage={canManageOrg}
              onChange={setTypes}
            />
          )}
        </section>
      ) : (
        <section className="card">
          {!company || loading ? (
            <div className="card-pad"><FormSkeleton compact fields={4} /></div>
          ) : (
            <PublicHolidays
              token={token}
              companyId={company.id}
              branchId={branch?.id}
              countryId={branch?.country_id}
              rows={holidays}
              canManage={canManageOrg}
              onChange={setHolidays}
            />
          )}
        </section>
      )}
    </>
  );
}
