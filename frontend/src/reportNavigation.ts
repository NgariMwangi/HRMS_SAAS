export const generalReports = [
  { key: "headcount", title: "Headcount", description: "Current employee records by branch, department and employment status.", permissions: ["people.view_all", "people.manage"] },
  { key: "payroll", title: "Payroll", description: "Saved payroll results with separate totals for each currency.", permissions: ["payroll.manage"] },
  { key: "attendance", title: "Attendance", description: "Recorded attendance, lateness, absences and completed clock hours.", permissions: ["attendance.manage"] },
  { key: "leave", title: "Leave", description: "Leave requests, approval status and requested days by leave type.", permissions: ["leave.view_all", "leave.manage"] },
  { key: "movement", title: "Employee movement", description: "Hires, exits and other recorded employment changes.", permissions: ["lifecycle.view_all", "lifecycle.manage"] },
];
export function canVisitReports(path: string, has: (key: string) => boolean) {
  if (!has("reports.view")) return false;
  const key = path.split("/")[3];
  if (!key) return generalReports.some(r => r.permissions.some(has));
  const report = generalReports.find(r => r.key === key);
  return !!report && report.permissions.some(has);
}
