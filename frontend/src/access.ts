import { canVisitPerformance } from "./performanceNavigation";
import { canVisitRecruitment } from "./recruitmentNavigation";
import { canVisitReports } from "./reportNavigation";
export function canVisit(path: string, has: (permission: string) => boolean): boolean {
  const any = (...keys: string[]) => keys.some(has);
  if (path === "/app") return true;
  if (path === "/app/reports" || path.startsWith("/app/reports/")) return canVisitReports(path, has);
  if (path === "/app/recruitment" || path.startsWith("/app/recruitment/")) return canVisitRecruitment(path, has);
  if (path === "/app/performance" || path.startsWith("/app/performance/")) return canVisitPerformance(path, has);
  if (/^\/app\/people\/[^/]+\/salary$/.test(path)) return has("payroll.manage");
  if (path === "/app/people/new" || path.endsWith("/edit")) return has("people.manage");
  if (/^\/app\/people\/[^/]+\/documents$/.test(path)) return any("documents.view_all", "documents.view_own", "documents.manage");
  if (path.startsWith("/app/people")) return any("people.view_all", "people.view_team", "people.view_own", "people.manage");
  if (path === "/app/documents") return any("documents.view_all", "documents.manage");
  if (path === "/app/lifecycle") return any("lifecycle.view_all", "lifecycle.manage");
  if (path === "/app/leave") return any("leave.view_all", "leave.view_team", "leave.view_own", "leave.manage");
  if (path === "/app/attendance") return any("attendance.self", "attendance.manage");
  if (path.startsWith("/app/payroll")) return has("payroll.manage");
  if (path === "/app/settings") return any("organization.manage", "documents.manage", "access.manage_roles", "audit.view");
  if (["/app/companies", "/app/branches", "/app/departments", "/app/job-titles", "/app/integrations"].includes(path)) return has("organization.manage");
  return false;
}
