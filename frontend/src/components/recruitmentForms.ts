import type { Department, JobTitle, Branch } from "../types";
import type { RecruitmentField } from "./RecruitmentForm";
import { RecruitmentData, Person, candidateName, stageLabel } from "./recruitmentTypes";
export type RecruitmentFormState = { kind: "job" | "candidate" | "application" | "interview" | "feedback" | "offer" | "hire" | "decision"; id?: string; job?: string; candidate?: string; application?: string; endpoint?: string; status?: string; title?: string };
export const recruitmentOptions = (values: string[]) => values.map(v => ({ value: v, label: stageLabel(v) }));
export function recruitmentFormFields(form: RecruitmentFormState, data: RecruitmentData, people: Person[], departments: Department[], titles: JobTitle[], branches: Branch[], employeeId?: string | null): { title: string; note?: string; fields: RecruitmentField[]; submitLabel?: string } {
  const job = data.jobs.find(j => j.id === form.id); const candidate = data.candidates.find(c => c.id === form.id); const offer = data.offers.find(o => o.id === form.id);
  const appName = (id: string) => { const a = data.applications.find(a => a.id === id); return a ? `${candidateName(data.candidates.find(c => c.id === a.candidate_id))} · ${data.jobs.find(j => j.id === a.job_id)?.title}` : "Application"; };
  const appOptions = data.applications.filter(a => ["APPLIED", "SHORTLISTED", "INTERVIEW"].includes(a.stage)).map(a => ({ value: a.id, label: appName(a.id) }));
  const personOptions = people.map(p => ({ value: p.id, label: p.name }));
  if (form.kind === "job") return { title: job ? "Edit vacancy" : "Create a vacancy", note: "Save a draft, then open the vacancy when it is ready.", fields: [
    { name: "title", label: "Vacancy title", required: true, value: job?.title }, { name: "location", label: "Location", value: job?.location },
    { name: "department_id", label: "Department", type: "select", options: departments.map(d => ({ value: d.id, label: d.name })), value: job?.department_id },
    { name: "job_title_id", label: "Employee job title", type: "select", options: titles.map(t => ({ value: t.id, label: t.name })), value: job?.job_title_id, hint: "Used when a candidate becomes an employee." },
    { name: "employment_type", label: "Employment type", type: "select", required: true, options: recruitmentOptions(["FULL_TIME", "CONTRACT", "INTERN", "PROBATION"]), value: job?.employment_type || "FULL_TIME" },
    { name: "openings", label: "Number of openings", type: "number", min: 1, max: 1000, required: true, value: job?.openings || 1 },
    { name: "closing_date", label: "Application closing date", type: "date", value: job?.closing_date },
    { name: "manager_id", label: "Hiring manager / supervisor", type: "select", options: personOptions, value: job?.manager_id, hint: "Managers can view applicants for assigned vacancies." },
    { name: "description", label: "Job description", type: "textarea", required: true, value: job?.description }, { name: "requirements", label: "Requirements", type: "textarea", value: job?.requirements },
  ] };
  if (form.kind === "candidate") return { title: candidate ? "Edit candidate" : "Add a candidate", note: "Add applications and upload a CV from the candidate's profile.", fields: [
    { name: "first_name", label: "First name", required: true, value: candidate?.first_name }, { name: "last_name", label: "Last name", required: true, value: candidate?.last_name },
    { name: "email", label: "Email address", type: "email", required: true, value: candidate?.email }, { name: "phone", label: "Phone number", value: candidate?.phone },
    { name: "source", label: "How did they find us?", value: candidate?.source || "Direct application" }, { name: "notes", label: "HR notes", type: "textarea", value: candidate?.notes },
  ] };
  if (form.kind === "application") return { title: "Add an application", fields: [
    { name: "job_id", label: "Open vacancy", type: "select", required: true, options: data.jobs.filter(j => j.status === "OPEN").map(j => ({ value: j.id, label: j.title })), value: form.job },
    { name: "candidate_id", label: "Candidate", type: "select", required: true, options: data.candidates.filter(c => !c.employee_id).map(c => ({ value: c.id, label: `${candidateName(c)} · ${c.email}` })), value: form.candidate },
  ] };
  if (form.kind === "interview") return { title: "Schedule an interview", note: "Panel members need active logins with Recruitment interview permission. Times use your browser's local timezone.", fields: [
    { name: "application_id", label: "Application", type: "select", required: true, options: appOptions, value: form.application },
    { name: "title", label: "Interview name", required: true, value: "Interview" }, { name: "starts_at", label: "Date and time", type: "datetime-local", required: true },
    { name: "duration_minutes", label: "Duration in minutes", type: "number", min: 15, max: 480, required: true, value: 60 }, { name: "location", label: "Location or meeting link" },
    { name: "interviewer_ids", label: "Interviewers", type: "checks", options: people.filter(p => p.can_interview).map(p => ({ value: p.id, label: p.name })), hint: "Only employees with active logins and interview permission appear here." },
  ] };
  if (form.kind === "feedback") {
    const feedback = data.interviews.find(i => i.id === form.id)?.feedback[employeeId || ""];
    return { title: "Record interview feedback", fields: [
      { name: "rating", label: "Overall rating", type: "select", required: true, options: [1, 2, 3, 4, 5].map(n => ({ value: String(n), label: `${n} / 5` })), value: feedback?.rating },
      { name: "recommendation", label: "Recommendation", type: "select", required: true, options: recruitmentOptions(["PROCEED", "HOLD", "DO_NOT_PROCEED"]), value: feedback?.recommendation },
      { name: "comments", label: "Feedback and reasons", type: "textarea", required: true, value: feedback?.comments },
    ] };
  }
  if (form.kind === "offer") return { title: offer ? "Edit offer" : "Prepare an offer", note: "Save a draft, then mark it as issued after sharing it with the candidate. This does not send an email.", fields: [
    { name: "application_id", label: "Application", type: "select", required: true, options: offer ? [{ value: offer.application_id, label: appName(offer.application_id) }] : appOptions.filter(o => !data.offers.some(f => f.application_id === o.value)), value: offer?.application_id || form.application },
    { name: "salary", label: "Monthly gross salary", type: "number", min: 0.01, step: "0.01", required: true, value: offer?.salary }, { name: "currency", label: "Currency", required: true, value: offer?.currency || "KES" },
    { name: "start_date", label: "Expected start date", type: "date", required: true, value: offer?.start_date }, { name: "expires_on", label: "Offer expiry date", type: "date", value: offer?.expires_on },
    { name: "terms", label: "Offer terms", type: "textarea", value: offer?.terms },
  ] };
  if (form.kind === "hire") {
    const a = data.applications.find(a => a.id === form.application); const j = data.jobs.find(j => j.id === a?.job_id); const o = data.offers.find(o => o.application_id === form.application);
    const fields: RecruitmentField[] = [{ name: "branch_id", label: "Employee branch", type: "select", required: true, options: branches.map(b => ({ value: b.id, label: b.name })) },
      { name: "date_joined", label: "Start date", type: "date", required: true, value: o?.start_date }, { name: "work_email", label: "Work email (optional)", type: "email" }];
    if (j && ["CONTRACT", "INTERN", "PROBATION"].includes(j.employment_type)) fields.push({ name: "date_ended", label: "Employment end date", type: "date", required: ["INTERN", "PROBATION"].includes(j.employment_type) });
    return { title: "Create employee from accepted offer", note: `${appName(form.application!)}. Contact details, department, job title and supervisor will carry into the employee record.`, fields, submitLabel: "Create employee" };
  }
  return { title: form.title || "Record decision", submitLabel: "Confirm decision", fields: [{ name: "note", label: "Reason", type: "textarea", required: true }] };
}
