import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api, apiBlob } from "../../api";
import { LifecycleActions, LifecycleTimeline } from "../../components/LifecyclePanel";
import { NextOfKinList } from "../../components/NextOfKinFields";
import { SupervisorList } from "../../components/SupervisorFields";
import { ClockLoginCard } from "../../components/ClockLoginCard";
import PerformanceHistory from "../../components/PerformanceHistory";
import { LeaveBalances } from "../../components/LeaveBalances";
import { employeeName, suspensionPayText, type Department, type Employee, type JobTitle, type LeaveType, type LifecycleEvent, type NextOfKin, type Supervisor } from "../../types";
import { EmptyState, formatDate, ProfileSkeleton, StatusPill } from "../../ui";

export default function EmployeeProfile() {
  const { employeeId } = useParams();
  const navigate = useNavigate();
  const { token, user, company, allBranches, notify, hasPermission } = useWorkspace();
  const canManageOrg = hasPermission("people.manage");
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [events, setEvents] = useState<LifecycleEvent[]>([]);
  const [kin, setKin] = useState<NextOfKin[]>([]);
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [photo, setPhoto] = useState<string | null>(null);

  useEffect(() => {
    if (!employeeId) return;
    api<Employee>(`/employees/${employeeId}`, { token })
      .then((row) => {
        setEmployee(row);
        setError(null);
        return Promise.all([
          api<Department[]>(`/departments?company_id=${row.company_id}`, { token }),
          api<JobTitle[]>(`/job-titles?company_id=${row.company_id}`, { token }),
          hasPermission("lifecycle.view_all") || hasPermission("lifecycle.manage") || (hasPermission("lifecycle.view_own") && row.id === user.employee_id) ? api<LifecycleEvent[]>(`/employees/${row.id}/lifecycle`, { token }) : Promise.resolve([] as LifecycleEvent[]),
          api<NextOfKin[]>(`/employees/${row.id}/next-of-kin`, { token }),
          api<Supervisor[]>(`/employees/${row.id}/supervisors`, { token }),
          api<LeaveType[]>(`/leave-types?company_id=${row.company_id}`, { token }),
          row.has_photo ? apiBlob(`/employees/${row.id}/photo`, token) : Promise.resolve(null),
        ]).then(([deptRows, titleRows, timeline, kinRows, supervisorRows, typeRows, photoUrl]) => {
          setDepartments(deptRows);
          setTitles(titleRows);
          setEvents(timeline);
          setKin(kinRows);
          setSupervisors(supervisorRows);
          setLeaveTypes(typeRows);
          setPhoto(photoUrl);
        });
      })
      .catch((err: Error) => setError(err.message));
  }, [employeeId, token, company?.id]);

  if (error && !employee) {
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow"><Link to="/app/people">Employees</Link></div>
            <h1>Employee</h1>
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

  const companyBranches = allBranches.filter((row) => row.company_id === employee.company_id);
  const canViewDocuments = hasPermission("documents.view_all") || hasPermission("documents.manage") || (hasPermission("documents.view_own") && user.employee_id === employee.id);
  const canViewLifecycle = hasPermission("lifecycle.view_all") || hasPermission("lifecycle.manage") || (hasPermission("lifecycle.view_own") && user.employee_id === employee.id);
  const canViewLeave = hasPermission("leave.view_all") || hasPermission("leave.manage") || (hasPermission("leave.view_own") && user.employee_id === employee.id) || (hasPermission("leave.view_team") && supervisors.some((row) => row.id === user.employee_id));
  const title = titles.find((row) => row.id === employee.job_title_id);
  const department = departments.find((row) => row.id === employee.department_id);
  const site = companyBranches.find((row) => row.id === employee.branch_id);

  return (
    <div className="profile-page">
      <div className="page-head">
        <div>
          <div className="eyebrow"><Link to="/app/people">Employees</Link></div>
          <div className="title-row">
            <h1>{employeeName(employee)}</h1>
            <StatusPill value={employee.status} />
          </div>
          <p className="profile-sub">
            <span>{employee.employee_number}</span>
            <span>{title?.name ?? "No title"}</span>
            <span>{site?.name ?? "No branch"}</span>
          </p>
        </div>
        <div className="actions">
          {hasPermission("payroll.manage") ? <Link className="btn small" to={`/app/people/${employee.id}/salary`}>Salary</Link> : null}
          {canViewDocuments ? <Link className="btn small" to={`/app/people/${employee.id}/documents`}>View documents</Link> : null}
          {canManageOrg ? (
            <Link className="btn ghost small" to={`/app/people/${employee.id}/edit`}>Edit</Link>
          ) : null}
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
            <div><dt>Other names</dt><dd>{employee.other_names || "—"}</dd></div>
            <div><dt>Work email</dt><dd>{employee.email ?? "—"}</dd></div>
            <div><dt>Personal email</dt><dd>{employee.personal_email ?? "—"}</dd></div>
            <div><dt>Phone</dt><dd>{employee.phone ?? "—"}</dd></div>
            <div><dt>Second phone</dt><dd>{employee.other_phone ?? "—"}</dd></div>
            <div><dt>Date of birth</dt><dd>{formatDate(employee.date_of_birth)}</dd></div>
            <div><dt>ID no.</dt><dd>{employee.id_number ?? "—"}</dd></div>
            <div><dt>NSSF no.</dt><dd>{employee.nssf_no ?? "—"}</dd></div>
            <div><dt>PIN number</dt><dd>{employee.pin_number ?? "—"}</dd></div>
            <div><dt>SHIF no.</dt><dd>{employee.shif_no ?? "—"}</dd></div>
            <div><dt>Job title</dt><dd>{title?.name ?? "—"}</dd></div>
            <div><dt>Department</dt><dd>{department?.name ?? "—"}</dd></div>
            <div><dt>Branch</dt><dd>{site?.name ?? "—"}</dd></div>
            <div><dt>Type</dt><dd>{employee.employment_type.replaceAll("_", " ").toLowerCase()}</dd></div>
            <div><dt>Start date</dt><dd>{formatDate(employee.date_joined)}</dd></div>
            {employee.status === "SUSPENDED" && suspensionPayText(employee) ? (
              <div><dt>Pay during suspension</dt><dd>{suspensionPayText(employee)}</dd></div>
            ) : null}
            {employee.date_ended ? <div><dt>End date</dt><dd>{formatDate(employee.date_ended)}</dd></div> : null}
            {employee.previous_employee_id ? (
              <div>
                <dt>Previous record</dt>
                <dd><Link className="row-link" to={`/app/people/${employee.previous_employee_id}`}>Open</Link></dd>
              </div>
            ) : null}
          </dl>
        </div>
      </section>

      <SupervisorList rows={supervisors} hrefFor={(row) => `/app/people/${row.id}`} />
      {hasPermission("performance.view_all") || (hasPermission("performance.view_own") && user.employee_id === employee.id) || hasPermission("performance.view_team") ? <PerformanceHistory companyId={employee.company_id} employeeId={employee.id} /> : null}

      <ClockLoginCard
        employee={employee}
        token={token}
        canManageHr={hasPermission("people.manage")}
        canEditLogin={user.role === "OWNER" && hasPermission("people.manage")}
        canResetDevice={hasPermission("attendance.manage")}
        onChanged={setEmployee}
        notify={notify}
      />

      <section className="card">
        <div className="card-head">
          <div>
            <h3>Salary</h3>
            <p>Add a new amount when pay changes, or correct a row that was entered wrong.</p>
          </div>
          {hasPermission("payroll.manage") ? <Link className="btn small" to={`/app/people/${employee.id}/salary`}>Open salary</Link> : null}
        </div>
      </section>

      <NextOfKinList rows={kin} />

      {canViewLeave ? <section className="card">
        <LeaveBalances
          token={token}
          companyId={employee.company_id}
          employees={[employee]}
          types={leaveTypes}
          canManageHr={hasPermission("leave.manage")}
          employeeId={employee.id}
        />
      </section> : null}

      <section className="card">
        <div className="card-head">
          <div>
            <h3>Documents</h3>
            <p>Uploads and lifecycle files for this person.</p>
          </div>
          {canViewDocuments ? <Link className="btn small" to={`/app/people/${employee.id}/documents`}>View documents</Link> : null}
        </div>
      </section>

      {canViewLifecycle ? <section className="card">
        <div className="card-head">
          <div>
            <h3>Lifecycle</h3>
            <p>Employment changes stay on this record. Status is not edited on the form.</p>
          </div>
        </div>
        {hasPermission("lifecycle.manage") ? (
          <div className="card-pad">
            <LifecycleActions
              employee={employee}
              token={token}
              apiBase=""
              departments={departments}
              titles={titles}
              branches={companyBranches}
              canAct
              onChanged={(result) => {
                setEmployee(result.employee);
                setEvents((current) => [result.event, ...current]);
                notify(`${employeeName(result.employee)} updated.`);
                if (result.new_employee) navigate(`/app/people/${result.new_employee.id}`);
              }}
            />
          </div>
        ) : null}
        <LifecycleTimeline
          events={events}
          departments={departments}
          titles={titles}
          profilePath={(id) => `/app/people/${id}`}
          token={token}
          apiBase=""
        />
      </section> : null}
    </div>
  );
}
