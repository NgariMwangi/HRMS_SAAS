import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api, apiBlob, apiUpload } from "../../api";
import { NextOfKinFields } from "../../components/NextOfKinFields";
import { SupervisorFields } from "../../components/SupervisorFields";
import {
  employeeName,
  nextOfKinError,
  nextOfKinFromRow,
  nextOfKinPayload,
  type Department,
  type Employee,
  type JobTitle,
  type NextOfKin,
  type NextOfKinDraft,
  type Supervisor,
} from "../../types";
import { EmptyState, FormSkeleton, PageHeader } from "../../ui";

const steps = ["Personal", "Contact", "Role", "Branch", "Review"];
const REQUIRED_PERIOD_TYPES = new Set(["INTERN", "PROBATION"]);
const END_DATE_TYPES = new Set(["INTERN", "PROBATION", "CONTRACT"]);

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function daysBetween(start: string, end: string): string {
  if (!start || !end) return "";
  const from = new Date(`${start}T00:00:00`);
  const to = new Date(`${end}T00:00:00`);
  return String(Math.round((to.getTime() - from.getTime()) / 86400000));
}

type FormState = {
  first_name: string;
  other_names: string;
  last_name: string;
  date_of_birth: string;
  id_number: string;
  nssf_no: string;
  pin_number: string;
  shif_no: string;
  email: string;
  personal_email: string;
  phone: string;
  other_phone: string;
  job_title_id: string;
  department_id: string;
  employment_type: string;
  date_joined: string;
  period_days: string;
  date_ended: string;
  branch_id: string;
};

const empty: FormState = {
  first_name: "",
  other_names: "",
  last_name: "",
  date_of_birth: "",
  id_number: "",
  nssf_no: "",
  pin_number: "",
  shif_no: "",
  email: "",
  personal_email: "",
  phone: "",
  other_phone: "",
  job_title_id: "",
  department_id: "",
  employment_type: "FULL_TIME",
  date_joined: "",
  period_days: "",
  date_ended: "",
  branch_id: "",
};

function fromEmployee(row: Employee, fallbackBranch: string): FormState {
  return {
    first_name: row.first_name,
    other_names: row.other_names ?? "",
    last_name: row.last_name,
    date_of_birth: row.date_of_birth ?? "",
    id_number: row.id_number ?? "",
    nssf_no: row.nssf_no ?? "",
    pin_number: row.pin_number ?? "",
    shif_no: row.shif_no ?? "",
    email: row.email ?? "",
    personal_email: row.personal_email ?? "",
    phone: row.phone ?? "",
    other_phone: row.other_phone ?? "",
    job_title_id: row.job_title_id ?? "",
    department_id: row.department_id ?? "",
    employment_type: row.employment_type,
    date_joined: row.date_joined ?? "",
    period_days: daysBetween(row.date_joined ?? "", row.date_ended ?? ""),
    date_ended: row.date_ended ?? "",
    branch_id: row.branch_id || fallbackBranch,
  };
}

function stepFields(form: FormState, stepIndex: number): Record<string, string | null> {
  if (stepIndex === 0) {
    return {
      first_name: form.first_name.trim(),
      other_names: form.other_names.trim() || null,
      last_name: form.last_name.trim(),
      date_of_birth: form.date_of_birth || null,
      id_number: form.id_number.trim() || null,
      nssf_no: form.nssf_no.trim() || null,
      pin_number: form.pin_number.trim() || null,
      shif_no: form.shif_no.trim() || null,
    };
  }
  if (stepIndex === 1) {
    return {
      email: form.email.trim() || null,
      personal_email: form.personal_email.trim() || null,
      phone: form.phone.trim() || null,
      other_phone: form.other_phone.trim() || null,
    };
  }
  if (stepIndex === 2) {
    return {
      job_title_id: form.job_title_id || null,
      department_id: form.department_id || null,
      employment_type: form.employment_type,
      date_joined: form.date_joined || null,
      date_ended: END_DATE_TYPES.has(form.employment_type) ? form.date_ended || null : null,
    };
  }
  if (stepIndex === 3) {
    return { branch_id: form.branch_id };
  }
  return {};
}

export default function EmployeeCreate() {
  const navigate = useNavigate();
  const { employeeId: routeId } = useParams();
  const [params] = useSearchParams();
  const isEdit = Boolean(routeId);
  const { token, company, branch, allBranches, notify, hasPermission } = useWorkspace();
  const canManageOrg = hasPermission("people.manage");
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>({ ...empty, branch_id: branch?.id ?? "" });
  const [employeeId, setEmployeeId] = useState(routeId ?? params.get("employee") ?? "");
  const [employeeNumber, setEmployeeNumber] = useState("");
  const [companyId, setCompanyId] = useState(company?.id ?? "");
  const [incompletePeriod, setIncompletePeriod] = useState(false);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoSaved, setPhotoSaved] = useState(false);
  const [kin, setKin] = useState<NextOfKinDraft[]>([]);
  const [colleagues, setColleagues] = useState<Employee[]>([]);
  const [supervisorIds, setSupervisorIds] = useState<string[]>([]);
  const photoInput = useRef<HTMLInputElement>(null);
  const hydrated = useRef("");

  const existingId = routeId ?? params.get("employee");
  const companyBranches = allBranches.filter((row) => row.company_id === (companyId || company?.id));

  useEffect(() => {
    const scope = companyId || company?.id;
    if (!scope) return;
    Promise.all([
      api<Department[]>(`/departments?company_id=${scope}`, { token }),
      api<JobTitle[]>(`/job-titles?company_id=${scope}`, { token }),
      api<Employee[]>(`/employees?company_id=${scope}&status=ALL`, { token }),
    ]).then(([deptRows, titleRows, people]) => {
      setDepartments(deptRows.filter((row) => row.status === "ACTIVE"));
      setTitles(titleRows.filter((row) => row.status === "ACTIVE"));
      setColleagues(people);
    }).catch((err: Error) => setError(err.message));
  }, [companyId, company?.id, token]);

  useEffect(() => {
    if (branch?.id && !form.branch_id && !isEdit) {
      setForm((current) => ({ ...current, branch_id: branch.id }));
    }
  }, [branch?.id, isEdit]);

  useEffect(() => {
    if (!existingId || hydrated.current === existingId) return;
    hydrated.current = existingId;
    setLoading(true);
    api<Employee>(`/employees/${existingId}`, { token })
      .then((row) => {
        setEmployeeId(row.id);
        setEmployeeNumber(row.employee_number);
        setCompanyId(row.company_id);
        setIncompletePeriod(REQUIRED_PERIOD_TYPES.has(row.employment_type) && (!row.date_joined || !row.date_ended));
        setForm(fromEmployee(row, branch?.id ?? ""));
        setError(null);
        setPhotoSaved(row.has_photo);
        return Promise.all([
          api<NextOfKin[]>(`/employees/${row.id}/next-of-kin`, { token }),
          api<Supervisor[]>(`/employees/${row.id}/supervisors`, { token }),
          row.has_photo ? apiBlob(`/employees/${row.id}/photo`, token) : Promise.resolve(null),
        ]).then(([kinRows, supervisors, url]) => {
          setKin(kinRows.map(nextOfKinFromRow));
          setSupervisorIds(supervisors.map((item) => item.id));
          if (url) setPhotoPreview(url);
        });
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [existingId, token, branch?.id]);

  function bind(name: keyof FormState) {
    return {
      value: form[name],
      onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const value = event.target.value;
        setForm((current) => {
          const next = { ...current, [name]: value };
          if (name === "job_title_id") {
            const title = titles.find((row) => row.id === value);
            if (title?.department_id) next.department_id = title.department_id;
          }
          if (name === "employment_type" && !END_DATE_TYPES.has(value)) {
            next.date_ended = "";
            next.period_days = "";
          }
          if (name === "date_joined" && END_DATE_TYPES.has(next.employment_type)) {
            const days = Number(next.period_days);
            if (value && next.period_days !== "" && Number.isFinite(days) && days >= 0) {
              next.date_ended = addDays(value, days);
            } else if (value && next.date_ended) {
              next.period_days = daysBetween(value, next.date_ended);
            }
          }
          if (name === "period_days" && next.date_joined) {
            const days = Number(value);
            if (Number.isFinite(days) && days >= 0) next.date_ended = addDays(next.date_joined, days);
          }
          if (name === "date_ended") {
            next.period_days = daysBetween(next.date_joined, value);
          }
          return next;
        });
      },
    };
  }

  function validate(stepIndex: number): string | null {
    if (stepIndex === 0 && (!form.first_name.trim() || !form.last_name.trim())) {
      return "First name and last name are required.";
    }
    if (stepIndex === 1) {
      const emailOk = (value: string) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
      if (!emailOk(form.email.trim())) return "Enter a valid work email or leave it blank.";
      if (!emailOk(form.personal_email.trim())) return "Enter a valid personal email or leave it blank.";
      return nextOfKinError(kin);
    }
    if (stepIndex === 2 && END_DATE_TYPES.has(form.employment_type)) {
      if (REQUIRED_PERIOD_TYPES.has(form.employment_type) && !incompletePeriod && (!form.date_joined || !form.date_ended)) {
        return "Start date and end date are required for intern and probation.";
      }
      if (form.date_ended && form.date_joined && form.date_ended < form.date_joined) {
        return "End date must be on or after the start date.";
      }
    }
    if (stepIndex === 3 && !form.branch_id) {
      return "Branch is required.";
    }
    return null;
  }

  async function persist(stepIndex: number): Promise<Employee | null> {
    if (!canManageOrg || !company) return null;
    const problem = validate(stepIndex);
    if (problem) throw new Error(problem);

    const fields = stepFields(form, stepIndex);
    let saved: Employee | null = null;
    if (employeeId) {
      if (Object.keys(fields).length > 0) {
        saved = await api<Employee>(`/employees/${employeeId}`, {
          method: "PATCH",
          token,
          body: JSON.stringify(fields),
        });
      }
    } else {
      const branchId = form.branch_id || branch?.id;
      if (!branchId) {
        throw new Error("This company needs a branch before a person can be saved.");
      }
      saved = await api<Employee>("/employees", {
        method: "POST",
        token,
        body: JSON.stringify({
          company_id: company.id,
          branch_id: branchId,
          ...fields,
        }),
      });
      setEmployeeId(saved.id);
      setEmployeeNumber(saved.employee_number);
      setCompanyId(saved.company_id);
      navigate(`/app/people/new?employee=${saved.id}`, { replace: true });
    }

    if (saved) setIncompletePeriod(REQUIRED_PERIOD_TYPES.has(saved.employment_type) && (!saved.date_joined || !saved.date_ended));
    const id = saved?.id ?? employeeId;
    if (stepIndex === 0 && photoFile && id) {
      await apiUpload<Employee>(`/employees/${id}/photo`, photoFile, token);
      setPhotoFile(null);
      setPhotoSaved(true);
    }
    if (stepIndex === 1 && id) {
      await api<NextOfKin[]>(`/employees/${id}/next-of-kin`, {
        method: "PUT",
        token,
        body: JSON.stringify({ items: nextOfKinPayload(kin) }),
      });
    }
    if (stepIndex === 2 && id) {
      await api<Supervisor[]>(`/employees/${id}/supervisors`, {
        method: "PUT",
        token,
        body: JSON.stringify({ supervisor_ids: supervisorIds.filter(Boolean) }),
      });
    }
    return saved;
  }

  async function saveThenGo(nextStep: number) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await persist(step);
      setStep(nextStep);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this step");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (step < steps.length - 1) {
      await saveThenGo(step + 1);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = employeeId ? await persist(step) : await persist(0);
      const id = saved?.id ?? employeeId;
      notify(`${employeeName(form)} saved.`);
      navigate(`/app/people/${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save employee");
    } finally {
      setBusy(false);
    }
  }

  const title = isEdit ? "Edit employee" : "Add employee";

  if (!canManageOrg) {
    return (
      <>
        <PageHeader title={title} description="Only owners and admins can change people." />
        <section className="card">
          <EmptyState title="You cannot change employees" note="Ask a workspace owner to update this record." />
        </section>
      </>
    );
  }

  if (loading) {
    return <FormSkeleton />;
  }

  if (isEdit && error && !employeeId) {
    return (
      <>
        <PageHeader title={title} />
        <section className="card">
          <EmptyState title="Employee not found in this workspace" note={error} />
        </section>
      </>
    );
  }

  const selectedTitle = titles.find((row) => row.id === form.job_title_id);
  const selectedDept = departments.find((row) => row.id === form.department_id);
  const selectedBranch = companyBranches.find((row) => row.id === form.branch_id);

  return (
    <>
      <PageHeader
        title={title}
        description={`${company?.name ?? "This company"}. Continue saves this step, then moves on.`}
        actions={employeeId ? <Link className="btn ghost small" to={`/app/people/${employeeId}`}>Profile</Link> : null}
      />
      <div className="stepper">
        {steps.map((label, index) => (
          <button
            key={label}
            className={`step${index === step ? " current" : ""}${index < step ? " done" : ""}`}
            type="button"
            disabled={busy || (!employeeId && index > 0)}
            onClick={() => {
              if (index === step) return;
              void saveThenGo(index);
            }}
          >
            <small>Step {index + 1}</small>
            <strong>{label}</strong>
          </button>
        ))}
      </div>
      <form className="card card-pad" onSubmit={onSubmit}>
        {employeeNumber ? (
          <p className="muted" style={{ marginTop: 0 }}>{isEdit ? "Editing" : "Saved as"} {employeeNumber}.</p>
        ) : null}
        {step === 0 ? (
          <div className="form-grid">
            <label>First name <span className="req">*</span><input required={step === 0} {...bind("first_name")} /></label>
            <label>Other names<input {...bind("other_names")} placeholder="Middle or other given names" /></label>
            <label>Last name <span className="req">*</span><input required={step === 0} {...bind("last_name")} /></label>
            <label>Date of birth<input type="date" {...bind("date_of_birth")} /></label>
            <label>ID no.<input {...bind("id_number")} autoComplete="off" /></label>
            <label>NSSF no.<input {...bind("nssf_no")} autoComplete="off" /></label>
            <label>PIN number<input {...bind("pin_number")} autoComplete="off" /></label>
            <label>SHIF no.<input {...bind("shif_no")} autoComplete="off" /></label>
            <label style={{ gridColumn: "1 / -1" }}>
              Passport photo
              <input
                ref={photoInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="user"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  setPhotoFile(file);
                  setPhotoPreview((current) => {
                    if (current?.startsWith("blob:")) URL.revokeObjectURL(current);
                    return file ? URL.createObjectURL(file) : current;
                  });
                }}
              />
            </label>
            {photoPreview ? (
              <div className="passport-edit">
                <img className="passport-photo" src={photoPreview} alt="Passport preview" />
                <button
                  className="btn ghost small"
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    if (photoPreview.startsWith("blob:")) URL.revokeObjectURL(photoPreview);
                    setPhotoFile(null);
                    setPhotoPreview(null);
                    if (photoInput.current) photoInput.current.value = "";
                    if (employeeId && photoSaved) {
                      setBusy(true);
                      try {
                        await api(`/employees/${employeeId}/photo`, { method: "DELETE", token });
                        setPhotoSaved(false);
                        notify("Passport photo removed.");
                      } catch (err) {
                        setError(err instanceof Error ? err.message : "Could not remove photo");
                      } finally {
                        setBusy(false);
                      }
                    }
                  }}
                >
                  Remove
                </button>
              </div>
            ) : null}
            <p className="muted" style={{ gridColumn: "1 / -1" }}>
              JPEG, PNG, or WebP, up to 10 MB. Saved when you continue.
            </p>
          </div>
        ) : null}
        {step === 1 ? (
          <>
            <div className="form-grid">
              <label>Work email<input type="email" {...bind("email")} /></label>
              <label>Personal email<input type="email" {...bind("personal_email")} /></label>
              <label>Phone<input {...bind("phone")} /></label>
              <label>Second phone<input {...bind("other_phone")} /></label>
            </div>
            <NextOfKinFields rows={kin} onChange={setKin} />
          </>
        ) : null}
        {step === 2 ? (
          <>
          <div className="form-grid">
            <label>Job title
              <select {...bind("job_title_id")}>
                <option value="">Select</option>
                {titles.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label>Department
              <select {...bind("department_id")}>
                <option value="">Select</option>
                {departments.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label>
              Employment type
              <select {...bind("employment_type")}>
                <option value="FULL_TIME">Full-time</option>
                <option value="CONTRACT">Contract</option>
                <option value="INTERN">Intern</option>
                <option value="PROBATION">Probation</option>
              </select>
            </label>
            <label>Start date<input type="date" {...bind("date_joined")} /></label>
            {END_DATE_TYPES.has(form.employment_type) ? (
              <>
                <label>Duration (days)<input type="number" min={0} step={1} {...bind("period_days")} placeholder="e.g. 90" /></label>
                <label>End date<input type="date" min={form.date_joined || undefined} {...bind("date_ended")} /></label>
                <p className="muted" style={{ gridColumn: "1 / -1" }}>
                  {REQUIRED_PERIOD_TYPES.has(form.employment_type)
                    ? incompletePeriod ? "This existing record has missing employment dates. You can save changes and fill in either date when available." : "Enter how many days after the start date, or pick the end date on the calendar. Either one fills in the other."
                    : "Optional for contract. Enter how many days after the start date, or pick the end date on the calendar."}
                </p>
              </>
            ) : null}
          </div>
            <SupervisorFields
              people={colleagues}
              excludeId={employeeId ?? undefined}
              selectedIds={supervisorIds}
              onChange={setSupervisorIds}
            />
          </>
        ) : null}
        {step === 3 ? (
          <div className="form-grid">
            <label>
              Branch <span className="req">*</span>
              <select required={step === 3} {...bind("branch_id")}>
                <option value="">Select</option>
                {companyBranches.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <p className="muted" style={{ gridColumn: "1 / -1" }}>
              Country, timezone, and currency come from the branch. Statutory payroll is not entered here.
            </p>
          </div>
        ) : null}
        {step === 4 ? (
          <>
            {photoPreview ? <img className="passport-photo" src={photoPreview} alt="Passport preview" /> : null}
            <dl className="meta-grid">
              <div><dt>Name</dt><dd>{employeeName(form) || "—"}</dd></div>
              <div><dt>ID no.</dt><dd>{form.id_number || "—"}</dd></div>
              <div><dt>NSSF no.</dt><dd>{form.nssf_no || "—"}</dd></div>
              <div><dt>PIN number</dt><dd>{form.pin_number || "—"}</dd></div>
              <div><dt>SHIF no.</dt><dd>{form.shif_no || "—"}</dd></div>
              <div><dt>Work email</dt><dd>{form.email || "—"}</dd></div>
              <div><dt>Personal email</dt><dd>{form.personal_email || "—"}</dd></div>
              <div><dt>Phone</dt><dd>{form.phone || "—"}</dd></div>
              <div><dt>Second phone</dt><dd>{form.other_phone || "—"}</dd></div>
              <div>
                <dt>Next of kin</dt>
                <dd>
                  {nextOfKinPayload(kin).length
                    ? nextOfKinPayload(kin).map((row) => `${row.name} (${row.relationship})`).join(", ")
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Supervisors</dt>
                <dd>
                  {supervisorIds.filter(Boolean).length
                    ? supervisorIds.filter(Boolean).map((id) => {
                      const person = colleagues.find((row) => row.id === id);
                      return person ? employeeName(person) : id;
                    }).join(", ")
                    : "—"}
                </dd>
              </div>
              <div><dt>Role</dt><dd>{selectedTitle?.name ?? "—"}</dd></div>
              <div><dt>Department</dt><dd>{selectedDept?.name ?? "—"}</dd></div>
              <div><dt>Type</dt><dd>{form.employment_type.replaceAll("_", " ").toLowerCase()}</dd></div>
              <div><dt>Start date</dt><dd>{form.date_joined || "—"}</dd></div>
              {END_DATE_TYPES.has(form.employment_type) ? (
                <div><dt>End date</dt><dd>{form.date_ended || "—"}</dd></div>
              ) : null}
              <div><dt>Branch</dt><dd>{selectedBranch?.name ?? "—"}</dd></div>
            </dl>
          </>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        <div className="actions" style={{ marginTop: 16, justifyContent: "space-between" }}>
          <button className="btn ghost" type="button" onClick={() => setStep((current) => Math.max(current - 1, 0))} disabled={step === 0 || busy}>
            Back
          </button>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Saving…" : step === steps.length - 1 ? "Open profile" : "Save and continue"}
          </button>
        </div>
      </form>
    </>
  );
}
