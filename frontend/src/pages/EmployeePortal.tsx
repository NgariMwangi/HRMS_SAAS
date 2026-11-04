import PayslipDocument from "../components/PayslipDocument";
import { appraisalNoticePath } from "../performanceNavigation";
import { FormEvent, useEffect, useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "../context/WorkspaceContext";
import { Card, EmptyState, formatDate, formatDateTime, PageHeader, PageSkeleton, StatusPill } from "../ui";
import { ThemeToggle } from "../theme";
import type { Employee, LeaveType, PublicHoliday, LifecycleEvent } from "../types";
import { LifecycleTimeline } from "../components/LifecyclePanel";
import { employeeName } from "../types";
import MyAttendance from "../components/MyAttendance";
import { LeaveRequests } from "../components/LeaveRequests";
import { LeaveBalances } from "../components/LeaveBalances";
import { EmployeeDocuments } from "../components/EmployeeDocuments";
import AppraisalsHub from "../components/AppraisalsHub";
import type { Notice } from "../components/performanceTypes";
import { EmployeeImprovementPlans, EmployeeInterviewTasks } from "../components/EmployeeWorkPlans";
import { IconHome, IconPeople, IconClock, IconCalendar, IconPay, IconDoc, IconTarget, IconBell, IconSettings, IconBriefcase } from "../components/icons";
import GoogleSignIn from "../components/GoogleSignIn";
import "../performance.css";
import "../employee-portal.css";
import "../portal-modules.css";

type Profile = { employee: Employee; company_name: string; branch_name: string; department_name: string; job_title_name: string; google_linked: boolean };
type Contact = { name: string; relationship: string; phone: string; other_phone?: string | null; email?: string | null; address?: string | null };
type Slip = { id: string; employee_name: string; employee_number: string; period_start: string; period_end: string; currency_code: string; gross: string; basic: string | null; employee_deductions: string; employer_contributions: string; net: string; lines: Array<{ id: string; name: string; kind: string; party: string; amount: string }> };
type ClockRow = { id: string; work_on: string; status: string; checked_in_at: string | null; checked_out_at: string | null };
const navigation = [
  ["", "Overview", "", ""], ["profile", "My profile", "", "people.view_own"],
  ["attendance", "Attendance", "", "attendance.self"], ["leave", "Leave", "", "leave.view_own"],
  ["payslips", "Payslips", "", "payroll.view_own"], ["documents", "Documents", "", "documents.view_own"],
  ["performance", "My appraisal", "", "performance.view_own"], ["improvement-plans", "Improvement plans", "", "performance.view_own"],
  ["history", "Employment history", "", "lifecycle.view_own"], ["interviews", "My interviews", "", "recruitment.interview"],
  ["notifications", "Notifications", "", "performance.view_own"], ["account", "Account", "", ""],
];
const portalIcons: Record<string, typeof IconHome> = { "": IconHome, profile: IconPeople, attendance: IconClock, leave: IconCalendar, payslips: IconPay, documents: IconDoc, performance: IconTarget, "improvement-plans": IconTarget, history: IconClock, interviews: IconBriefcase, notifications: IconBell, account: IconSettings };
function PortalIcon({ path }: { path: string }) { const Icon = portalIcons[path] || IconHome; return <Icon />; }

export default function EmployeePortal() {
  const { section = "" } = useParams(); const navigate = useNavigate();
  const { user, token, company, branch, setCompanyId, setBranchId, signOut, hasPermission: has } = useWorkspace();
  const [profile, setProfile] = useState<Profile | null>(null); const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    api<Profile>("/employee-portal/me").then(value => { if (active) { setProfile(value); setError(""); } }).catch((err: Error) => { if (active) { setProfile(null); setError(err.message); } });
    return () => { active = false; };
  }, [user.id, user.employee_id, revision]);
  useEffect(() => {
    if (!profile) return;
    if (company?.id !== profile.employee.company_id) setCompanyId(profile.employee.company_id);
    else if (branch?.id !== profile.employee.branch_id) setBranchId(profile.employee.branch_id);
  }, [profile, company?.id, branch?.id]);
  if (!profile) return error ? <div className="portal-unavailable"><Card title="Employee portal unavailable" padded><p role="alert">{error}</p><button className="btn" onClick={signOut}>Sign out</button><Link className="btn ghost" to="/app">Open HR workspace</Link></Card></div> : <PageSkeleton />;
  if (company?.id !== profile.employee.company_id || branch?.id !== profile.employee.branch_id) return <PageSkeleton />;
  const allowed = navigation.filter(item => !item[3] || has(item[3]));
  const current = allowed.find(item => item[0] === section);
  return <div className="employee-portal">
    <aside className="portal-sidebar no-print"><Link to="/employee" className="portal-brand"><span className="mark">H</span><span>HRMS<small>Employee portal</small></span></Link>
      <div className="portal-company">{profile.company_name}<small>{profile.branch_name}</small></div>
      <nav aria-label="Employee portal">{allowed.map(([path, title]) => <NavLink end key={path} to={`/employee${path ? `/${path}` : ""}`}><span aria-hidden="true"><PortalIcon path={path} /></span>{title}</NavLink>)}</nav>
      {user.role !== "EMPLOYEE" && <Link className="quiet-link" to="/app">Open HR workspace</Link>}
      <div className="portal-sidebar-footer"><ThemeToggle /><button className="btn ghost small" onClick={signOut}>Sign out</button></div>
    </aside>
    <main className="portal-main"><header className="portal-topbar no-print"><span>{current?.[1] ?? "Page unavailable"}</span><Link to="/employee/profile">{employeeName(profile.employee)}<span className="portal-avatar">{profile.employee.first_name[0]}{profile.employee.last_name[0]}</span></Link></header>
      <div className="portal-content" key={section}>
        {!current ? <EmptyState title="Page unavailable" note="This page is not available for your account." /> :
        section === "profile" ? <MyProfile profile={profile} refresh={() => setRevision(value => value + 1)} /> :
        section === "attendance" ? <Attendance /> : section === "leave" ? <MyLeave employee={profile.employee} /> :
        section === "payslips" ? <Payslips /> : section === "documents" ? <><PageHeader title="My documents" description="View and download the files held by your HR team." /><EmployeeDocuments employeeId={profile.employee.id} companyId={profile.employee.company_id} token={token} apiBase="" canManage={false} profilePath={() => "/employee/profile"} /></> :
        section === "improvement-plans" ? <EmployeeImprovementPlans /> : section === "history" ? <><PageHeader title="My employment history" description="Your appointments and employment changes." /><EmploymentHistory employee={profile.employee} /></> : section === "interviews" ? <EmployeeInterviewTasks companyId={profile.employee.company_id} /> : section === "performance" ? <MyPerformance employee={profile.employee} /> : section === "notifications" ? <Notifications companyId={profile.employee.company_id} /> :
        section === "account" ? <Account profile={profile} refresh={() => setRevision(value => value + 1)} /> : <Overview profile={profile} go={path => navigate(`/employee/${path}`)} />}
      </div>
      <footer className="portal-footer no-print">Need help with your records or an account issue? Contact your HR team.</footer>
    </main>
  </div>;
}

function Overview({ profile, go }: { profile: Profile; go: (path: string) => void }) {
  const { hasPermission: has } = useWorkspace();
  const [summary, setSummary] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const load = () => { void api<Record<string, number>>("/employee-portal/summary").then(value => { setSummary(value); setError(""); }).catch((err: Error) => setError(err.message)); };
    load(); window.addEventListener("focus", load); return () => window.removeEventListener("focus", load);
  }, [profile.employee.id]);
  return <><div className="portal-welcome"><div className="eyebrow">{profile.company_name}</div><h1>Hello, {profile.employee.first_name}.</h1><p>Your work, your growth, and your day ahead.</p><div className="actions"><StatusPill value={profile.employee.status} /><span>{profile.job_title_name || profile.employee.employee_number} · {profile.department_name || profile.branch_name}</span></div></div>
    {error && <p className="error" role="alert">{error}</p>}
    {summary && <div className="portal-stat-grid">{([["pending_leave", "Leave awaiting approval", "leave"], ["active_appraisals", "Active appraisals", "performance"], ["documents", "Your documents", "documents"], ["unread_notifications", "Unread updates", "notifications"]]).filter(([key]) => summary[key] !== undefined).map(([key, label, path]) => <button className="portal-stat" key={key} onClick={() => go(path)}><strong>{summary[key]}</strong><span>{label}</span></button>)}</div>}
    <div className="portal-quick-grid">{navigation.filter(item => item[0] && item[0] !== "account" && (!item[3] || has(item[3]))).map(([path, title]) => <button className="portal-quick" key={path} onClick={() => go(path)}><span aria-hidden="true"><PortalIcon path={path} /></span><strong>{title}</strong><small>{({ profile: "Your details and emergency contacts", attendance: "Clock in and view your history", leave: "Request time off and check balances", payslips: "Your approved earnings and deductions", documents: "Your HR files, ready to download", performance: "Your appraisal, feedback and development", notifications: "Updates and upcoming deadlines", "improvement-plans": "Agreed objectives and support", history: "Your employment changes", interviews: "Assigned panels and your feedback" } as Record<string, string>)[path]}</small><span className="portal-arrow" aria-hidden="true">→</span></button>)}</div>
    {has("attendance.self") && <MyAttendance />}
    <Card title="Your employment" padded><div className="portal-detail-grid"><Detail label="Employee number" value={profile.employee.employee_number} /><Detail label="Company" value={profile.company_name} /><Detail label="Branch" value={profile.branch_name} /><Detail label="Joined" value={formatDate(profile.employee.date_joined)} /></div></Card>
  </>;
}

function Detail({ label, value }: { label: string; value?: string | null }) { return <div><small className="muted">{label}</small><p>{value || "—"}</p></div>; }

function MyProfile({ profile, refresh }: { profile: Profile; refresh: () => void }) {
  const { hasPermission: has, notify } = useWorkspace(); const employee = profile.employee;
  const [phone, setPhone] = useState(employee.phone ?? ""); const [otherPhone, setOtherPhone] = useState(employee.other_phone ?? ""); const [email, setEmail] = useState(employee.personal_email ?? "");
  const [contacts, setContacts] = useState<Contact[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { api<Contact[]>("/employee-portal/emergency-contacts").then(rows => setContacts(rows.map(({ name, relationship, phone, other_phone, email, address }) => ({ name, relationship, phone, other_phone, email, address })))).catch((err: Error) => setError(err.message)).finally(() => setLoading(false)); }, []);
  async function save(event: FormEvent, area: "profile" | "emergency-contacts") {
    event.preventDefault(); setBusy(true); setError("");
    try { await api(`/employee-portal/${area}`, { method: area === "profile" ? "PATCH" : "PUT", body: JSON.stringify(area === "profile" ? { phone: phone || null, other_phone: otherPhone || null, personal_email: email || null } : { items: contacts }) }); notify("Your details were saved."); refresh(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <><PageHeader title="My profile" description="Keep your contact and emergency details up to date." />
    <Card title={employeeName(employee)} padded><div className="portal-detail-grid"><Detail label="Work email" value={employee.email} /><Detail label="Employee number" value={employee.employee_number} /><Detail label="Department" value={profile.department_name} /><Detail label="Job title" value={profile.job_title_name} /><Detail label="Employment type" value={employee.employment_type.replaceAll("_", " ")} /><Detail label="Date joined" value={formatDate(employee.date_joined)} /></div><p className="muted">Contact HR to correct your employment or legal records.</p></Card>
    {error && <p className="error" role="alert">{error}</p>}
    <Card title="Contact details" padded><form onSubmit={event => void save(event, "profile")}><fieldset disabled={!has("people.update_own_contact") || busy}><div className="form-grid"><label>Personal email<input type="email" maxLength={255} value={email} onChange={event => setEmail(event.target.value)} /></label><label>Phone<input type="tel" maxLength={50} value={phone} onChange={event => setPhone(event.target.value)} /></label><label>Alternative phone<input type="tel" maxLength={50} value={otherPhone} onChange={event => setOtherPhone(event.target.value)} /></label></div>{has("people.update_own_contact") && <button className="btn">Save contact details</button>}</fieldset></form></Card>
    <Card title="Emergency contacts" padded>{loading ? <p role="status">Loading contacts…</p> : <form onSubmit={event => void save(event, "emergency-contacts")}><fieldset disabled={!has("people.update_own_contact") || busy}>{contacts.map((contact, index) => <div className="portal-contact" key={index}><div className="form-grid">{(["name", "relationship", "phone", "email", "address"] as const).map(key => <label key={key}>{key === "name" ? "Full name" : key[0].toUpperCase() + key.slice(1)}<input type={key === "email" ? "email" : key === "phone" ? "tel" : "text"} required={["name", "relationship", "phone"].includes(key)} maxLength={key === "phone" ? 50 : key === "relationship" ? 80 : key === "name" ? 200 : 255} value={contact[key] ?? ""} onChange={event => setContacts(rows => rows.map((row, at) => at === index ? { ...row, [key]: event.target.value || (key === "email" || key === "address" ? null : "") } : row))} /></label>)}</div>{has("people.update_own_contact") && <button className="btn ghost small" type="button" onClick={() => setContacts(rows => rows.filter((_, at) => at !== index))}>Remove contact</button>}</div>)}{!contacts.length && <p className="muted">No emergency contacts added yet.</p>}{has("people.update_own_contact") && <div className="actions"><button className="btn ghost" type="button" disabled={contacts.length >= 20} onClick={() => setContacts(rows => [...rows, { name: "", relationship: "", phone: "" }])}>Add contact</button><button className="btn">Save emergency contacts</button></div>}</fieldset></form>}</Card>
    {has("lifecycle.view_own") && <EmploymentHistory employee={employee} />}
  </>;
}

function EmploymentHistory({ employee }: { employee: Employee }) {
  const { token } = useWorkspace(); const [events, setEvents] = useState<LifecycleEvent[] | null>(null); const [error, setError] = useState("");
  useEffect(() => { api<LifecycleEvent[]>(`/employees/${employee.id}/lifecycle`).then(setEvents).catch((err: Error) => setError(err.message)); }, [employee.id]);
  return <Card title="Employment history" padded>{error ? <p className="error" role="alert">{error}</p> : events ? <LifecycleTimeline events={events} departments={[]} titles={[]} profilePath={() => "/employee/profile"} token={token} apiBase="" /> : <p role="status">Loading employment history…</p>}</Card>;
}

function Attendance() {
  const [rows, setRows] = useState<ClockRow[]>([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const [start, setStart] = useState(""); const [end, setEnd] = useState("");
  const load = () => { setLoading(true); api<ClockRow[]>(`/employee-portal/attendance?limit=366${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`).then(value => { setRows(value); setError(""); }).catch((err: Error) => setError(err.message)).finally(() => setLoading(false)); };
  useEffect(load, [start, end]);
  return <><MyAttendance /><Card title="Attendance history" padded><div className="form-grid"><label>From<input type="date" value={start} onChange={event => setStart(event.target.value)} /></label><label>To<input type="date" min={start} value={end} onChange={event => setEnd(event.target.value)} /></label></div><button className="btn ghost small" onClick={load}>Refresh history</button>{error && <p className="error" role="alert">{error}</p>}{loading ? <p role="status">Loading attendance…</p> : rows.length ? <div className="portal-table"><table><thead><tr><th>Date</th><th>Status</th><th>Clock in</th><th>Clock out</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{formatDate(row.work_on)}</td><td><StatusPill value={row.status.replaceAll("_", " ")} /></td><td>{formatDateTime(row.checked_in_at)}</td><td>{formatDateTime(row.checked_out_at)}</td></tr>)}</tbody></table></div> : <EmptyState title="No attendance records" note="Your recorded attendance will appear here." />}</Card></>;
}

function MyLeave({ employee }: { employee: Employee }) {
  const { token, notify } = useWorkspace(); const [types, setTypes] = useState<LeaveType[]>([]); const [holidays, setHolidays] = useState<PublicHoliday[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [tab, setTab] = useState("Requests");
  useEffect(() => { Promise.all([api<LeaveType[]>(`/leave-types?company_id=${employee.company_id}`), api<PublicHoliday[]>(`/public-holidays?company_id=${employee.company_id}&branch_id=${employee.branch_id}`)]).then(([a, b]) => { setTypes(a); setHolidays(b); }).catch((err: Error) => setError(err.message)).finally(() => setLoading(false)); }, [employee.company_id, employee.branch_id]);
  return <><PageHeader title="My leave" description="Plan your time off and follow each approval." /><div className="page-tabs">{["Requests", "Balances", "Holidays"].map(item => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>{error && <p className="error" role="alert">{error}</p>}{loading ? <PageSkeleton /> : <Card padded>{tab === "Requests" ? <LeaveRequests token={token} companyId={employee.company_id} employees={[employee]} types={types} canManageHr={false} canManageTeam={false} ownOnly selfEmployeeId={employee.id} notify={notify} /> : tab === "Balances" ? <LeaveBalances token={token} companyId={employee.company_id} employees={[employee]} types={types} employeeId={employee.id} canManageHr={false} /> : holidays.length ? <div className="portal-table"><table><thead><tr><th>Holiday</th><th>Date</th></tr></thead><tbody>{holidays.map(row => <tr key={row.id}><td>{row.name}</td><td>{row.observed_on ? formatDate(row.observed_on) : `${row.day}/${row.month} each year`}</td></tr>)}</tbody></table></div> : <EmptyState title="No holidays published" note="Your HR team will publish holidays here." />}</Card>}</>;
}

function Payslips() {
  const { token } = useWorkspace();
  const [rows, setRows] = useState<Slip[]>([]); const [selected, setSelected] = useState<Slip | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  useEffect(() => { let active = true; api<Slip[]>("/employee-portal/payslips").then(value => { if (active) { setRows(value); setSelected(value[0] ?? null); } }).catch((err: Error) => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  return <><PageHeader title="My payslips" description="Your approved pay statements, ready to view and download as PDF." />{error && <p className="error" role="alert">{error}</p>}{loading ? <PageSkeleton /> : !rows.length ? <Card padded><EmptyState title="No payslips yet" note="Your payslips will appear after HR approves payroll." /></Card> : <label>Pay period<select value={selected?.id ?? ""} onChange={event => setSelected(rows.find(row => row.id === event.target.value) ?? null)}>{rows.map(row => <option key={row.id} value={row.id}>{formatDate(row.period_start)} ? {formatDate(row.period_end)}</option>)}</select></label>}
    {selected && <PayslipDocument key={selected.id} path={`/employee-portal/payslips/${selected.id}`} token={token} />}
  </>;
}

function MyPerformance({ employee }: { employee: Employee }) {
  return <AppraisalsHub portal companyId={employee.company_id} />;
}

function Notifications({ companyId }: { companyId: string }) {
  const { notify } = useWorkspace(); const [rows, setRows] = useState<Notice[]>([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const load = () => api<Notice[]>(`/performance/notifications?company_id=${companyId}`).then(value => { setRows(value); setError(""); }).catch((err: Error) => setError(err.message)).finally(() => setLoading(false));
  useEffect(() => { void load(); window.addEventListener("focus", load); return () => window.removeEventListener("focus", load); }, [companyId]);
  async function read(row: Notice) { try { await api(`/performance/notifications/${row.id}/read`, { method: "POST" }); await load(); notify("Marked as read."); } catch (err) { setError((err as Error).message); } }
  return <><PageHeader title="My notifications" description="Performance updates and reminders for your account." />{error && <p className="error" role="alert">{error}</p>}{loading ? <PageSkeleton /> : rows.length ? rows.map(row => <Card key={row.id} padded><div className="portal-notice"><div><p>{row.message}</p><small className="muted">{formatDateTime(row.created_at)}</small></div><div className="actions">{(row.appraisal_id || row.event_key?.startsWith("simple:")) && <Link className="btn ghost small" to={appraisalNoticePath(row, true)}>View appraisal</Link>}{!row.read_at && <button className="btn small" onClick={() => void read(row)}>Mark read</button>}</div></div></Card>) : <Card padded><EmptyState title="You’re all caught up" note="New updates will appear here." /></Card>}</>;
}

function Account({ profile, refresh }: { profile: Profile; refresh: () => void }) {
  const { user, notify, reloadAccess } = useWorkspace(); const [current, setCurrent] = useState(""); const [next, setNext] = useState(""); const [confirm, setConfirm] = useState(""); const [googlePassword, setGooglePassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [loginEmail, setLoginEmail] = useState(user.email); const [emailPassword, setEmailPassword] = useState("");
  useEffect(() => { setLoginEmail(user.email); }, [user.email]);
  async function changeEmail(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      await api("/employee-portal/login", { method: "PATCH", body: JSON.stringify({ email: loginEmail.trim(), current_password: emailPassword }) });
      await reloadAccess(); setEmailPassword(""); refresh(); notify("Login email updated. Use your new email the next time you sign in.");
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function change(event: FormEvent) {
    event.preventDefault(); setError(""); if (next !== confirm) { setError("New passwords do not match."); return; } setBusy(true);
    try { await api("/employee-portal/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) }); setCurrent(""); setNext(""); setConfirm(""); notify("Password updated."); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <><PageHeader title="Account settings" description="Manage how you sign in to your employee account." /><Card title="Change login email" padded><form onSubmit={changeEmail}><fieldset disabled={busy}><div className="form-grid"><label>Login email<input type="email" autoComplete="username" required value={loginEmail} onChange={event => setLoginEmail(event.target.value)} /></label><label>Confirm current password<input type="password" autoComplete="current-password" required maxLength={72} value={emailPassword} onChange={event => setEmailPassword(event.target.value)} /></label></div><p className="muted">This changes your sign-in email. Your work and personal contact emails stay the same.</p><button className="btn" disabled={loginEmail.trim().toLowerCase() === user.email.toLowerCase()}>Update login email</button></fieldset></form></Card>{error && <p className="error" role="alert">{error}</p>}
    <Card title="Change password" padded><form onSubmit={change}><fieldset disabled={busy}><div className="form-grid"><label>Current password<input type="password" autoComplete="current-password" required maxLength={72} value={current} onChange={event => setCurrent(event.target.value)} /></label><label>New password<input type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={next} onChange={event => setNext(event.target.value)} /></label><label>Confirm new password<input type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={confirm} onChange={event => setConfirm(event.target.value)} /></label></div><button className="btn">Update password</button></fieldset></form></Card>
    <Card title="Sign in with Google" padded><p>{profile.google_linked ? "Your Google account is connected." : "Connect Google to sign in without entering your work password next time."}</p><label>Confirm current password<input type="password" autoComplete="current-password" maxLength={72} value={googlePassword} onChange={event => setGooglePassword(event.target.value)} /></label>{profile.google_linked ? <button className="btn ghost" disabled={busy || !googlePassword} onClick={() => { setBusy(true); void api("/auth/google/unlink", { method: "POST", body: JSON.stringify({ password: googlePassword }) }).then(() => { setGooglePassword(""); refresh(); notify("Google disconnected."); }).catch((err: Error) => setError(err.message)).finally(() => setBusy(false)); }}>Disconnect Google</button> : <GoogleSignIn disabled={busy || !googlePassword} onCredential={async credential => { await api("/auth/google/link", { method: "POST", credentials: "include", body: JSON.stringify({ credential, password: googlePassword }) }); setGooglePassword(""); refresh(); notify("Google connected."); }} />}</Card>
  </>;
}
