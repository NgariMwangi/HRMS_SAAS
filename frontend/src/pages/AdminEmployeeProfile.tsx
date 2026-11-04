import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { adminToken, api, apiBlob } from "../api";
import { ClockLoginCard } from "../components/ClockLoginCard";
import { LeaveBalances } from "../components/LeaveBalances";
import { LifecycleActions, LifecycleTimeline } from "../components/LifecyclePanel";
import { EmployeeDocuments } from "../components/EmployeeDocuments";
import { NextOfKinList } from "../components/NextOfKinFields";
import { SupervisorList } from "../components/SupervisorFields";
import type { Branch, Company, Department, Employee, JobTitle, LeaveType, LifecycleEvent, NextOfKin, Supervisor, TenantWorkspace } from "../types";
import { employeeName, suspensionPayText } from "../types";
import { EmptyState, formatDate, ProfileSkeleton, StatusPill } from "../ui";

export default function AdminEmployeeProfile() {
  const { tenantId, employeeId } = useParams();
  const navigate = useNavigate();
  const token = adminToken.get();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [branch, setBranch] = useState<Branch | null>(null);
  const [department, setDepartment] = useState<Department | null>(null);
  const [title, setTitle] = useState<JobTitle | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [events, setEvents] = useState<LifecycleEvent[]>([]);
  const [kin, setKin] = useState<NextOfKin[]>([]);
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      navigate("/admin/login");
      return;
    }
    if (!tenantId || !employeeId) return;
    const base = `/platform/tenants/${tenantId}`;
    api<Employee>(`${base}/employees/${employeeId}`, { token })
      .then(async (row) => {
        setEmployee(row);
        setError(null);
        const [workspace, timeline, kinRows, supervisorRows] = await Promise.all([
          api<TenantWorkspace>(`${base}/workspace`, { token }),
          api<LifecycleEvent[]>(`${base}/employees/${row.id}/lifecycle`, { token }),
          api<NextOfKin[]>(`${base}/employees/${row.id}/next-of-kin`, { token }),
          api<Supervisor[]>(`${base}/employees/${row.id}/supervisors`, { token }),
        ]);
        setCompany(workspace.companies.find((item) => item.id === row.company_id) ?? null);
        setBranches(workspace.branches.filter((item) => item.company_id === row.company_id));
        setBranch(workspace.branches.find((item) => item.id === row.branch_id) ?? null);
        setDepartments(workspace.departments.filter((item) => item.company_id === row.company_id));
        setDepartment(workspace.departments.find((item) => item.id === row.department_id) ?? null);
        setTitles(workspace.job_titles.filter((item) => item.company_id === row.company_id));
        setTitle(workspace.job_titles.find((item) => item.id === row.job_title_id) ?? null);
        setLeaveTypes((workspace.leave_types ?? []).filter((item) => item.company_id === row.company_id));
        setEvents(timeline);
        setKin(kinRows);
        setSupervisors(supervisorRows);
        const photoUrl = row.has_photo ? await apiBlob(`${base}/employees/${row.id}/photo`, token) : null;
        setPhoto(photoUrl);
      })
      .catch((err: Error) => setError(err.message));
  }, [navigate, token, tenantId, employeeId]);

  useEffect(() => {
    return () => {
      if (photo) URL.revokeObjectURL(photo);
    };
  }, [photo]);

  const back = `/admin/tenants/${tenantId}?tab=employees`;

  if (error && !employee) {
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow"><Link to={back}>Employees</Link></div>
            <h1>Employee</h1>
          </div>
        </div>
        <section className="card">
          <EmptyState title="Employee not found for this tenant" note={error} />
        </section>
      </>
    );
  }

  if (!employee || !token || !tenantId) {
    return <ProfileSkeleton />;
  }

  const base = `/platform/tenants/${tenantId}`;

  return (
    <div className="profile-page">
      <div className="page-head">
        <div>
          <div className="eyebrow"><Link to={back}>Employees</Link></div>
          <div className="title-row">
            <h1>{employeeName(employee)}</h1>
            <StatusPill value={employee.status} />
          </div>
          <p>
            {employee.employee_number}
            {" · "}
            {title?.name ?? "No title"}
            {" · "}
            {company?.name ?? "No company"}
          </p>
        </div>
        <div className="actions">
          <Link className="btn small" to={`/admin/tenants/${tenantId}/employees/${employee.id}/salary`}>Salary</Link>
          <Link className="btn ghost small" to={back}>Back to tenant</Link>
        </div>
      </div>

      <section className="card card-pad">
        <div className="profile-id">
          <div className="passport-frame">
            {photo ? (
              <img className="passport-photo" src={photo} alt={employeeName(employee)} />
            ) : (
              <div className="passport-photo is-empty">No passport photo</div>
            )}
            <small>Passport photo</small>
          </div>
          <dl className="meta-grid">
            <div><dt>Employee no.</dt><dd>{employee.employee_number}</dd></div>
            <div><dt>First name</dt><dd>{employee.first_name}</dd></div>
            <div><dt>Other names</dt><dd>{employee.other_names || "—"}</dd></div>
            <div><dt>Last name</dt><dd>{employee.last_name}</dd></div>
            <div><dt>Date of birth</dt><dd>{formatDate(employee.date_of_birth)}</dd></div>
            <div><dt>ID no.</dt><dd>{employee.id_number ?? "—"}</dd></div>
            <div><dt>NSSF no.</dt><dd>{employee.nssf_no ?? "—"}</dd></div>
            <div><dt>PIN number</dt><dd>{employee.pin_number ?? "—"}</dd></div>
            <div><dt>SHIF no.</dt><dd>{employee.shif_no ?? "—"}</dd></div>
            <div><dt>Work email</dt><dd>{employee.email ?? "—"}</dd></div>
            <div><dt>Personal email</dt><dd>{employee.personal_email ?? "—"}</dd></div>
            <div><dt>Phone</dt><dd>{employee.phone ?? "—"}</dd></div>
            <div><dt>Second phone</dt><dd>{employee.other_phone ?? "—"}</dd></div>
            <div><dt>Company</dt><dd>{company?.name ?? "—"}</dd></div>
            <div><dt>Branch</dt><dd>{branch ? `${branch.name} · ${branch.code}` : "—"}</dd></div>
            <div><dt>Department</dt><dd>{department?.name ?? "—"}</dd></div>
            <div><dt>Job title</dt><dd>{title?.name ?? "—"}</dd></div>
            <div><dt>Employment type</dt><dd>{employee.employment_type.replaceAll("_", " ").toLowerCase()}</dd></div>
            <div><dt>Start date</dt><dd>{formatDate(employee.date_joined)}</dd></div>
            {employee.date_ended ? <div><dt>End date</dt><dd>{formatDate(employee.date_ended)}</dd></div> : null}
            <div><dt>Status</dt><dd>{employee.status}</dd></div>
            {employee.status === "SUSPENDED" && suspensionPayText(employee) ? (
              <div><dt>Pay during suspension</dt><dd>{suspensionPayText(employee)}</dd></div>
            ) : null}
            {employee.previous_employee_id ? (
              <div>
                <dt>Previous record</dt>
                <dd><Link className="row-link" to={`/admin/tenants/${tenantId}/employees/${employee.previous_employee_id}`}>Open</Link></dd>
              </div>
            ) : null}
            <div><dt>Created</dt><dd>{formatDate(employee.created_at)}</dd></div>
            <div><dt>Updated</dt><dd>{formatDate(employee.updated_at)}</dd></div>
          </dl>
        </div>
      </section>

      {notice ? <p className="muted">{notice}</p> : null}

      <ClockLoginCard
        employee={employee}
        token={token}
        apiBase={base}
        canManageHr
        onChanged={setEmployee}
        notify={setNotice}
      />

      <section className="card">
        <div className="card-head">
          <div>
            <h3>Salary</h3>
            <p>Add a new amount when pay changes, or correct a row that was entered wrong.</p>
          </div>
          <Link className="btn small" to={`/admin/tenants/${tenantId}/employees/${employee.id}/salary`}>Open salary</Link>
        </div>
      </section>

      <SupervisorList
        rows={supervisors}
        hrefFor={(row) => `/admin/tenants/${tenantId}/employees/${row.id}`}
      />

      <NextOfKinList rows={kin} />

      <section className="card">
        <LeaveBalances
          token={token}
          apiBase={base}
          companyId={employee.company_id}
          employees={[employee]}
          types={leaveTypes}
          canManageHr
          employeeId={employee.id}
        />
      </section>

      <EmployeeDocuments
        employeeId={employee.id}
        companyId={employee.company_id}
        token={token}
        apiBase={base}
        canManage
      />

      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h3>Lifecycle</h3>
            <p>The same events as the tenant workspace. Status is not patched directly.</p>
          </div>
        </div>
        <LifecycleActions
          employee={employee}
          token={token}
          apiBase={base}
          departments={departments}
          titles={titles}
          branches={branches}
          canAct
          onChanged={(result) => {
            setEmployee(result.employee);
            setDepartment(departments.find((item) => item.id === result.employee.department_id) ?? null);
            setTitle(titles.find((item) => item.id === result.employee.job_title_id) ?? null);
            setBranch(branches.find((item) => item.id === result.employee.branch_id) ?? null);
            setEvents((current) => [result.event, ...current]);
            if (result.new_employee) {
              navigate(`/admin/tenants/${tenantId}/employees/${result.new_employee.id}`);
            }
          }}
        />
        <LifecycleTimeline
          events={events}
          departments={departments}
          titles={titles}
          profilePath={(id) => `/admin/tenants/${tenantId}/employees/${id}`}
          token={token}
          apiBase={base}
        />
      </section>
    </div>
  );
}
