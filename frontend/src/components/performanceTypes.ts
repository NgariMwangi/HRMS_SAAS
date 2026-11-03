export type Level = { value: string; label: string; description?: string; minimum: string; maximum: string };
export type Scale = { id: string; name: string; levels: Level[] };
export type Settings = {
  frequency: string; rating_scale_id: string | null; kpi_weight: string; competency_weight: string;
  require_self: boolean; require_manager: boolean; require_review: boolean; require_calibration: boolean;
  require_acknowledgement: boolean; employee_goal_creation: boolean; manager_goal_approval: boolean;
  auto_scoring: boolean; employee_view_manager: boolean; employee_view_calibration: boolean;
  development_threshold: string | null; pip_threshold: string | null;
};
export type Cycle = {
  company_id: string;
  id: string; name: string; frequency: string; start_date: string; end_date: string;
  status: string; version: number; windows: Record<string, { start: string; end: string }>;
  config: Settings & { rating_scale: Scale; goal_entry_roles?: string[] };
};
export type Person = { id: string; name: string; branch_id: string; department_id: string | null; job_title_id: string | null };
export type Competency = { id: string; name: string; definition: { name: string; description: string; category: string; indicators: string[]; weight: string; active: boolean; department_ids: string[]; job_title_ids: string[]; employee_ids: string[] } };
export type Rating = { id: string; rating: string; comment: string };
export type Assessment = { goals?: Rating[]; competencies?: Rating[]; summary?: string; achievements?: string; challenges?: string; support?: string; career_interests?: string; recommendations?: string; submitted_at?: string };
export type GoalDefinition = { title: string; description: string; category: string; measurement: string; direction: string; target: string | null; unit: string; weight: string; priority: string; start_date: string; due_date: string; scoring_cap: string };
export type Goal = { id: string; title: string; weight: string; progress: string; actual: string | null; status: string; version: number; definition: GoalDefinition; approval: Record<string, string> };
export type Action = { id: string; title: string; due_date: string; owner_id: string; status: string; progress: string; version: number; details: Record<string, string> };
export type Appraisal = {
  company_id: string;
  self_submitted: boolean; manager_submitted: boolean;
  id: string; status: string; version: number; finalized_at: string | null; goal_count: number; completed_goals: number; goal_progress: string;
  participant: { id: string; employee_id: string; manager_id: string | null; reviewer_id: string | null; context: Record<string, string | null> };
  cycle: Cycle; self_assessment: Assessment; manager_assessment: Assessment;
  competencies: Array<Competency["definition"] & { id: string }>;
  review: Record<string, unknown>; acknowledgement: Record<string, string>;
  scores: Record<string, string | boolean>; goals?: Goal[];
  check_ins?: Array<{ id: string; meeting_date: string; details: Record<string, string | string[]> }>;
  development_actions?: Action[]; events?: Array<{ id: string; action: string; created_at: string; details: Record<string, unknown> }>;
};
export type PIP = { id: string; employee_id: string; manager_id: string; hr_owner_id: string; appraisal_id: string | null; start_date: string; end_date: string; status: string; version: number; details: { reason: string; issues: string; support: string; review_frequency_days: number; objectives: Array<{ title: string; target: string; expected_standard: string }>; outcome?: string }; reviews: Array<{ id: string; meeting_date: string; details: { notes: string; next_review: string | null; objective_progress: string[] } }> };
export type Notice = { event_key?: string; id: string; message: string; read_at: string | null; appraisal_id: string | null; created_at: string };
export type Report = { participants: number; goals_completed: number; self_completed: number; manager_completed: number; reviews_pending: number; calibration_pending: number; finalized: number; average_score: string | null; active_pips: number; overdue_development: number; rating_distribution: Record<string, number>; departments: Record<string, { participants: number; finalized: number; average: string | null }>; branches: Report["departments"]; managers: Report["departments"]; competency_gaps: Record<string, string>; goal_achievement: Array<{ title: string; progress: string; actual: string | null; status: string }>; development_progress: Action[]; pip_status: Array<{ id: string; employee_id: string; status: string; end_date: string }>; records: Array<{ appraisal_id: string; employee_name: string; department_name: string; branch_name: string; manager_name: string; cycle: string; status: string; score: string | null; rating: string | null; recommend_pip: boolean; recommend_development: boolean }> };

export const reviewStatus = (status: string) => status === "DRAFT" ? "Upcoming" : ["COMPLETED", "FINALIZED"].includes(status) ? "Completed" : "In progress";
export const reviewTask = (status: string) => ({ DRAFT: "Set up review", GOAL_SETTING: "Enter and approve goals", ACTIVE: "Update goal progress", SELF_ASSESSMENT: "Employee self-review", MANAGER_ASSESSMENT: "Manager assessment", REVIEW: "Discuss results", CALIBRATION: "Confirm ratings", FINALIZATION: "Acknowledge and finalize", COMPLETED: "View results" }[status] ?? status);
