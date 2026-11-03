export const performancePages = [
  { path: "my", title: "My appraisal", label: "My appraisal", description: "Complete your self-review and read published results.", permissions: ["performance.view_own"] },
  { path: "team", title: "Team appraisals", label: "Team appraisals", description: "Prepare forms, assess employees and record discussions.", permissions: ["performance.view_team", "performance.assess_team"] },
  { path: "reviews", title: "Manage appraisals", label: "Manage appraisals", description: "Set up reviews and follow each employee's next action.", permissions: ["performance.manage_cycles", "performance.view_all"] },
  { path: "templates", title: "Appraisal templates", label: "Templates", description: "Prepare reusable forms and clear assessment criteria.", permissions: ["performance.manage_cycles"] },
  { path: "reports", title: "Appraisal results", label: "Results", description: "View completion and published results.", permissions: ["performance.view_reports"] },
  { path: "archive", title: "Previous appraisals", label: "Previous appraisals", description: "Read historical performance records.", permissions: [] },
] as const;
export function canUsePerformance(has: (permission: string) => boolean) {
  return ["performance.view_own", "performance.view_team", "performance.view_all", "performance.manage_cycles", "performance.assess_team", "performance.view_reports"].some(has);
}
export function canVisitPerformance(path: string, has: (permission: string) => boolean) {
  if (!canUsePerformance(has)) return false;
  const section = path.split("/")[3] || "";
  if (["", "overview", "notifications", "records", "appraisals"].includes(section)) return true;
  const aliases: Record<string, string> = { settings: "templates", "rating-scales": "templates", competencies: "templates", calibration: "reviews" };
  const page = performancePages.find(item => item.path === (aliases[section] || section));
  return Boolean(page && (!page.permissions.length || page.permissions.some(has)));
}
// Existing deep links open the read-only archive.
export const appraisalSections: Record<string, string> = { goals: "Goals", "check-ins": "Check-ins", assessment: "Assessment", results: "Review & decision", development: "Development", history: "History" };
export function appraisalNoticePath(notice: { event_key?: string; appraisal_id?: string | null }, portal = false) {
  const identity = notice.event_key?.match(/^simple:([0-9a-f-]{36}):/i)?.[1];
  return identity ? portal ? `/employee/performance?record=${identity}` : `/app/performance/records/${identity}` : notice.appraisal_id ? portal ? `/employee/performance?appraisal=${notice.appraisal_id}` : `/app/performance/appraisals/${notice.appraisal_id}/results` : portal ? "/employee/performance" : "/app/performance/my";
}
