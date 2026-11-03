export const recruitmentPages = [
  { path: "overview", label: "Overview", description: "Hiring activity and your next steps." },
  { path: "jobs", label: "Jobs", description: "Create vacancies and manage applicants." },
  { path: "candidates", label: "Candidates", description: "Candidate profiles, CVs and application history." },
  { path: "interviews", label: "Interviews", description: "Interview schedules and panel feedback." },
  { path: "offers", label: "Offers", description: "Prepare offers, record responses and hire employees." },
  { path: "reports", label: "Reports", description: "Track applications and hiring progress." },
];
export function canVisitRecruitment(path: string, has: (key: string) => boolean) {
  const section = path.split("/")[3] || "overview";
  if (!recruitmentPages.some(p => p.path === section)) return false;
  if (["offers", "reports"].includes(section)) return has("recruitment.manage");
  return ["recruitment.manage", "recruitment.view_assigned", "recruitment.interview"].some(has);
}
