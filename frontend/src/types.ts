export type Permission = { key: string; label: string; group: string };
export type AccessRole = { id: string; key: string; name: string; description: string | null; is_system: boolean; locked: boolean; permissions: string[]; user_count: number };
export type MyAccess = { role: string; role_name: string | null; permissions: string[]; employee_id: string | null };
export type LeavePerson = Pick<Employee, "id" | "company_id" | "branch_id" | "first_name" | "other_names" | "last_name" | "employee_number" | "status">;
export type EmployeeSummary = LeavePerson;

export type Country = {
  id: string;
  code: string;
  name: string;
  default_timezone: string | null;
  is_active: boolean;
  default_currency: {
    code: string;
    name: string;
    symbol: string | null;
    decimal_places: number;
  } | null;
};

export type Tenant = {
  id: string;
  name: string;
  subscription_tier: string;
  status: string;
  trial_ends_at: string | null;
  created_at: string | null;
  user_count?: number;
  company_count?: number;
};

export type User = {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  employee_id?: string | null;
};

export type Branch = {
  id: string;
  company_id: string;
  country_id?: string;
  currency_id?: string | null;
  name: string;
  code: string;
  status: string;
  timezone: string | null;
  city: string | null;
  address?: string | null;
  state?: string | null;
  postal_code?: string | null;
};

export type Company = {
  id: string;
  tenant_id: string;
  name: string;
  legal_name: string | null;
  registration_number?: string | null;
  email?: string | null;
  phone?: string | null;
  website?: string | null;
  status: string;
  branches?: Branch[];
};

export type Department = {
  id: string;
  company_id: string;
  name: string;
  code: string | null;
  description: string | null;
  status: string;
};

export type NextOfKin = {
  id: string;
  name: string;
  relationship: string;
  phone: string;
  other_phone: string | null;
  email: string | null;
  address: string | null;
  sort_order: number;
};

export type NextOfKinDraft = {
  name: string;
  relationship: string;
  phone: string;
  other_phone: string;
  email: string;
  address: string;
};

export const NEXT_OF_KIN_RELATIONSHIPS = [
  "Spouse",
  "Parent",
  "Child",
  "Sibling",
  "Guardian",
  "Relative",
  "Friend",
  "Other",
] as const;

export function emptyNextOfKin(): NextOfKinDraft {
  return { name: "", relationship: "", phone: "", other_phone: "", email: "", address: "" };
}

export function nextOfKinFromRow(row: NextOfKin): NextOfKinDraft {
  return {
    name: row.name,
    relationship: row.relationship,
    phone: row.phone,
    other_phone: row.other_phone ?? "",
    email: row.email ?? "",
    address: row.address ?? "",
  };
}

export function nextOfKinHasValue(row: NextOfKinDraft): boolean {
  return Boolean(
    row.name.trim() ||
    row.relationship.trim() ||
    row.phone.trim() ||
    row.other_phone.trim() ||
    row.email.trim() ||
    row.address.trim(),
  );
}

export function nextOfKinPayload(rows: NextOfKinDraft[]): Array<{
  name: string;
  relationship: string;
  phone: string;
  other_phone: string | null;
  email: string | null;
  address: string | null;
}> {
  return rows.filter(nextOfKinHasValue).map((row) => ({
    name: row.name.trim(),
    relationship: row.relationship.trim(),
    phone: row.phone.trim(),
    other_phone: row.other_phone.trim() || null,
    email: row.email.trim() || null,
    address: row.address.trim() || null,
  }));
}

export function nextOfKinError(rows: NextOfKinDraft[]): string | null {
  const emailOk = (value: string) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  for (const row of rows) {
    if (!nextOfKinHasValue(row)) continue;
    if (!row.name.trim() || !row.relationship.trim() || !row.phone.trim()) {
      return "Each next of kin needs a name, relationship, and phone, or remove that row.";
    }
    if (!emailOk(row.email.trim())) return "Enter a valid next of kin email or leave it blank.";
  }
  return null;
}

export type Employee = {
  id: string;
  company_id: string;
  branch_id: string;
  department_id: string | null;
  job_title_id: string | null;
  employee_number: string;
  first_name: string;
  other_names: string | null;
    last_name: string;
  date_of_birth: string | null;
  id_number: string | null;
  nssf_no: string | null;
  pin_number: string | null;
  shif_no: string | null;
  email: string | null;
  personal_email: string | null;
  phone: string | null;
  other_phone: string | null;
  employment_type: string;
  date_joined: string | null;
  date_ended: string | null;
  has_photo: boolean;
  previous_employee_id?: string | null;
  status: string;
  suspension_pay_treatment?: string | null;
  suspension_pay_deduction_percent?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  has_clock_device?: boolean;
  clock_login_email?: string | null;
};

export type PayLine = {
  id: string;
  kind: string;
  name: string;
  amount: string;
  sort_order: number;
};

export type Compensation = {
  id: string;
  company_id: string;
  employee_id: string;
  effective_from: string;
  structure: string;
  gross_amount: string | null;
  basic_amount: string | null;
  computed_gross: string;
  computed_basic: string | null;
  voluntary_pension: string | null;
  pension_scheme: string | null;
  currency_id: string;
  created_at?: string | null;
  lines: PayLine[];
};

export type PayrollSettings = {
  company_id: string;
  frequency: string;
  salary_structure: string;
  country_id: string | null;
  country_code: string | null;
  country_name: string | null;
  currency_id: string | null;
  currency_code: string | null;
  currency_symbol: string | null;
  pack_status: string | null;
  pack_version: number | null;
  pack_effective_from: string | null;
};

export type PayslipLine = {
  id: string;
  code: string;
  name: string;
  party: string;
  kind: string;
  amount: string;
  sort_order: number;
  employee_deduction_id?: string | null;
  employee_benefit_id?: string | null;
};

export type DeductionCategory = "PERSONAL" | "COMPANY";

export type DeductionType = {
  id: string;
  company_id: string;
  name: string;
  category: DeductionCategory;
  default_amount: string | null;
  is_active: boolean;
};

export type EmployeeDeduction = {
  id: string;
  employee_id: string;
  deduction_type_id: string;
  type_name: string;
  category: DeductionCategory;
  frequency: "RECURRING" | "ONE_OFF";
  amount: string;
  start_date: string;
  end_date: string | null;
  total_amount: string | null;
  reference: string | null;
  status: "ACTIVE" | "STOPPED";
  recovered: string;
  balance: string | null;
  created_at?: string | null;
};

export type BenefitType = {
  id: string;
  company_id: string;
  name: string;
  default_amount: string | null;
  is_active: boolean;
};

export type EmployeeBenefit = {
  id: string;
  employee_id: string;
  benefit_type_id: string;
  type_name: string;
  note: string | null;
  frequency: "RECURRING" | "ONE_OFF";
  amount: string;
  start_date: string;
  end_date: string | null;
  status: "ACTIVE" | "STOPPED";
  paid: string;
  created_at?: string | null;
};

export const deductionCategoryLabel: Record<DeductionCategory, string> = {
  PERSONAL: "Personal",
  COMPANY: "Company scheme",
};

export type Payslip = {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_number: string;
  gross: string;
  basic: string | null;
  employee_deductions: string;
  employer_contributions: string;
  net: string;
  lines: PayslipLine[];
};

export type PayrollRun = {
  id: string;
  company_id: string;
  branch_id: string;
  period_start: string;
  period_end: string;
  status: string;
  payroll_pack_id: string;
  pack_version: number | null;
  country_code: string | null;
  currency_id: string;
  currency_code: string | null;
  gross_total: string;
  deduction_total: string;
  employer_total: string;
  net_total: string;
  skipped: number;
  created_at?: string | null;
  payslips: Payslip[];
};

export type PayrollPackSummary = {
  id: string;
  country_id: string;
  country_code: string | null;
  version: number;
  effective_from: string;
  status: string;
};

export type PayrollPackBand = {
  id: string;
  sort_order: number;
  from_amount: string;
  to_amount: string | null;
  rate_percent: string;
};

export type PayrollPackComponent = {
  id: string;
  code: string;
  name: string;
  party: string;
  formula_kind: string;
  base: string;
  percent: string | null;
  cap: string | null;
  floor: string | null;
  amount: string | null;
  min_amount: string | null;
  relief_key: string | null;
  reduces_taxable: boolean;
  sort_order: number;
  bands: PayrollPackBand[];
};

export type PayrollPackConstant = {
  id: string;
  key: string;
  amount: string;
};

export type PayrollPack = PayrollPackSummary & {
  components: PayrollPackComponent[];
  constants: PayrollPackConstant[];
};

export type AttendanceRow = {
  employee_id: string;
  employee_name: string;
  employee_number: string;
  company_id: string;
  branch_id: string;
  work_on: string;
  status: string;
  source: string | null;
  checked_in_at: string | null;
  checked_out_at: string | null;
  note: string | null;
  on_leave: boolean;
  has_clock_device: boolean;
  clock_login_email: string | null;
  record_id: string | null;
};

export type LifecycleAttachment = {
  id: string;
  filename: string;
  content_type: string;
};

export type LifecycleEvent = {
  id: string;
  company_id: string;
  employee_id: string;
  event_type: string;
  reason: string | null;
  effective_on: string;
  note: string | null;
  from_department_id: string | null;
  to_department_id: string | null;
  from_job_title_id: string | null;
  to_job_title_id: string | null;
  from_branch_id: string | null;
  to_branch_id: string | null;
  related_employee_id: string | null;
  created_by: string | null;
  created_at: string | null;
  employee_number?: string | null;
  employee_name?: string | null;
  attachments?: LifecycleAttachment[];
  pay_treatment?: string | null;
  pay_deduction_percent?: number | null;
  from_date_ended?: string | null;
  to_date_ended?: string | null;
  extension_days?: number | null;
  employment_type?: string | null;
};

export type LifecycleActionResult = {
  event: LifecycleEvent;
  employee: Employee;
  new_employee: Employee | null;
};

export type Supervisor = {
  id: string;
  employee_number: string;
  first_name: string;
  other_names: string | null;
  last_name: string;
  status: string;
};

export function employeeName(row: Pick<Employee, "first_name" | "other_names" | "last_name">): string {
  return [row.first_name, row.other_names, row.last_name].filter(Boolean).join(" ");
}

export function formatPayPercent(value: string | number | null | undefined): string {
  if (value == null || value === "") return "";
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return String(value);
  return Number.isInteger(amount) ? String(amount) : String(Math.round(amount * 100) / 100);
}

export function suspensionPayText(row: {
  pay_treatment?: string | null;
  pay_deduction_percent?: string | number | null;
  suspension_pay_treatment?: string | null;
  suspension_pay_deduction_percent?: string | number | null;
}): string | null {
  const treatment = row.pay_treatment ?? row.suspension_pay_treatment;
  const percent = row.pay_deduction_percent ?? row.suspension_pay_deduction_percent;
  if (treatment === "WITH_PAY") return "With pay";
  if (treatment === "WITHOUT_PAY") return "Without pay";
  if (treatment === "PARTIAL") {
    const shown = formatPayPercent(percent);
    return shown ? `${shown}% deducted` : "Percentage deducted";
  }
  return null;
}

export type JobTitle = {
  id: string;
  company_id: string;
  department_id: string | null;
  name: string;
  code: string | null;
  description: string | null;
  status: string;
};

export type TenantAuth = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_expires_in: number;
  tenant: Tenant;
  user: User;
  company: Company | null;
  branch: Branch | null;
};

export type PlatformAuth = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_expires_in: number;
  admin: { id: string; email: string; full_name: string; status: string };
};

export type Overview = {
  tenant_count: number;
  active_tenant_count: number;
  trial_count: number;
  user_count: number;
  company_count: number;
  branch_count: number;
};

export type TenantDetail = Tenant & {
  users: User[];
  companies: Company[];
};

export type TenantWorkspace = {
  tenant: Tenant;
  users: User[];
  companies: Company[];
  branches: Branch[];
  departments: Department[];
  job_titles: JobTitle[];
  document_categories: DocumentCategory[];
  leave_types: LeaveType[];
  employees: Employee[];
};

export type LeaveType = {
  id: string;
  company_id: string;
  name: string;
  days: string | number;
  accrued: boolean;
  accrual_per_month?: string | number;
  day_basis: "CALENDAR" | "WORKING" | string;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export function leaveDayBasisLabel(value: string): string {
  return value === "CALENDAR" ? "Calendar days" : "Working days";
}

export type LeaveBalance = {
  employee_id: string;
  employee_name: string;
  employee_number: string;
  leave_type_id: string;
  leave_type_name: string;
  year: number;
  accrued: boolean;
  unlimited: boolean;
  entitled: string | number;
  extra: string | number;
  used: string | number;
  pending: string | number;
  remaining: string | number | null;
};

export function formatLeaveDays(value: string | number | null | undefined, unlimited = false): string {
  if (unlimited || value == null || value === "") return "Unlimited";
  const amount = Number(value);
  if (Number.isNaN(amount)) return "—";
  return Number.isInteger(amount) ? String(amount) : amount.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export type PublicHoliday = {
  id: string;
  company_id: string;
  country_id?: string | null;
  name: string;
  kind: "YEARLY" | "ONCE" | string;
  month: number | null;
  day: number | null;
  observed_on: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function dayOrdinal(day: number): string {
  const teen = day % 100;
  if (teen >= 11 && teen <= 13) return `${day}th`;
  if (day % 10 === 1) return `${day}st`;
  if (day % 10 === 2) return `${day}nd`;
  if (day % 10 === 3) return `${day}rd`;
  return `${day}th`;
}

export function holidayWhen(row: PublicHoliday): string {
  if (row.kind === "ONCE" && row.observed_on) {
    const date = new Date(`${row.observed_on}T00:00:00`);
    return `${dayOrdinal(date.getDate())} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
  }
  if (row.month && row.day) {
    return `${dayOrdinal(row.day)} ${MONTHS[row.month - 1]}`;
  }
  return "—";
}

export function holidayKindLabel(value: string): string {
  return value === "ONCE" ? "One-off" : "Every year";
}

export type LeaveDecision = {
  id: string;
  step: string;
  decision: string;
  note: string | null;
  actor_user_id: string | null;
  actor_employee_id: string | null;
  actor_name?: string | null;
  created_at?: string | null;
};

export type LeaveRequest = {
  id: string;
  company_id: string;
  employee_id: string;
  employee_name: string;
  employee_number: string;
  leave_type_id: string;
  leave_type_name: string;
  day_basis: string;
  start_on: string;
  end_on: string;
  days: string | number;
  reason: string | null;
  requested_as: string;
  approval_mode: string;
  status: string;
  requested_by_user_id: string | null;
  requested_by_employee_id: string | null;
  requested_by_name?: string | null;
  decisions: LeaveDecision[];
  created_at?: string | null;
  updated_at?: string | null;
};

export function countLeaveDays(startOn: string, endOn: string, dayBasis: string): number {
  if (!startOn || !endOn || endOn < startOn) return 0;
  const start = new Date(`${startOn}T00:00:00`);
  const end = new Date(`${endOn}T00:00:00`);
  if (dayBasis === "CALENDAR") {
    return Math.round((end.getTime() - start.getTime()) / 86400000) + 1;
  }
  let days = 0;
  const cursor = new Date(start);
  while (cursor <= end) {
    const weekday = cursor.getDay();
    if (weekday !== 0 && weekday !== 6) days += 1;
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

export function leaveStatusLabel(value: string): string {
  if (value === "PENDING_SUPERVISOR") return "Waiting for supervisor";
  if (value === "PENDING_HR") return "Waiting for HR";
  if (value === "APPROVED") return "Approved";
  if (value === "REJECTED") return "Rejected";
  if (value === "CANCELLED") return "Cancelled";
  return value;
}

export function leaveRequestedAsLabel(value: string): string {
  if (value === "HR") return "HR";
  if (value === "EMPLOYEE") return "Employee";
  if (value === "SUPERVISOR") return "Supervisor";
  return value;
}

export type DocumentCategory = {
  id: string;
  company_id: string;
  name: string;
  system_key: string | null;
  locked: boolean;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export function uploadableCategories(rows: DocumentCategory[]): DocumentCategory[] {
  return rows.filter((row) => !row.locked);
}

export type CompanyDocument = {
  id: string;
  source: "UPLOAD" | "LIFECYCLE" | string;
  company_id: string;
  employee_id: string;
  employee_name?: string | null;
  employee_number?: string | null;
  category_id?: string | null;
  category?: string | null;
  locked?: boolean;
  filename: string;
  content_type: string;
  size?: number;
  issued_on?: string | null;
  expires_on?: string | null;
  note?: string | null;
  event_id?: string | null;
  event_type?: string | null;
  event_label?: string | null;
  created_at?: string | null;
};

export function groupDocumentsByCategory(
  rows: CompanyDocument[],
  categories: DocumentCategory[],
): { id: string; name: string; locked: boolean; rows: CompanyDocument[] }[] {
  const ordered = [...categories].sort(
    (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
  );
  const known = new Set(ordered.map((row) => row.id));
  const groups = ordered.map((category) => ({
    id: category.id,
    name: category.name,
    locked: category.locked,
    rows: rows.filter((row) => row.category_id === category.id),
  }));
  const other = rows.filter((row) => !row.category_id || !known.has(row.category_id));
  if (other.length) {
    groups.push({ id: "", name: "Uncategorized", locked: false, rows: other });
  }
  return groups.filter((group) => group.rows.length > 0);
}

export function documentFileType(filename: string, contentType?: string | null): string {
  const name = filename.toLowerCase();
  const type = (contentType || "").toLowerCase();
  if (name.endsWith(".pdf") || type.includes("pdf")) return "PDF";
  if (name.endsWith(".docx") || name.endsWith(".doc") || type.includes("word") || type.includes("msword")) {
    return "Word";
  }
  if (name.endsWith(".png") || type.includes("png")) return "PNG";
  if (name.endsWith(".jpg") || name.endsWith(".jpeg") || type.includes("jpeg")) return "JPEG";
  if (name.endsWith(".webp") || type.includes("webp")) return "WebP";
  if (name.endsWith(".txt") || type.startsWith("text/")) return "Text";
  const ext = name.includes(".") ? name.split(".").pop() : "";
  return ext ? ext.toUpperCase() : "File";
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    const kb = bytes / 1024;
    return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  }
  const mb = bytes / (1024 * 1024);
  return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
}

export function documentDownloadPath(apiBase: string, row: CompanyDocument): string {
  if (row.source === "LIFECYCLE" && row.event_id) {
    return `${apiBase}/employees/${row.employee_id}/lifecycle/${row.event_id}/attachments/${row.id}`;
  }
  return `${apiBase}/employees/${row.employee_id}/documents/${row.id}`;
}

export type AuditLog = {
  id: string;
  tenant_id: string | null;
  requester: string;
  action: string;
  request: string;
  method: string;
  path: string;
  status_code: number;
  outcome: "SUCCESS" | "FAILED" | string;
  response: string;
  created_at: string | null;
};

export type TenantSession = {
  tenant: Tenant;
  user: User;
  companyId?: string;
  branchId?: string;
};
