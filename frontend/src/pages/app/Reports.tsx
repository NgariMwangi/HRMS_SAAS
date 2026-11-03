import { useWorkspace } from "../../context/WorkspaceContext";
import { useNavigate, useParams } from "react-router-dom";
import GeneralReports from "../../components/GeneralReports";
import { EmptyState } from "../../ui";

export default function ReportsPage() {
  const { company, token, hasPermission } = useWorkspace();
  const { report } = useParams(); const navigate = useNavigate();
  if (!company) return <EmptyState title="Select a company" note="Select a company to view its reports." />;
  const href = (key?: string) => `/app/reports${key ? `/${key}` : ""}`;
  const canViewPeople = ["people.view_all", "people.manage"].some(hasPermission);
  return <GeneralReports key={`${company.id}-${report || "overview"}`} companyId={company.id} token={token} kind={report} selectReport={key => navigate(href(key))} reportHref={href} employeeHref={canViewPeople ? id => `/app/people/${id}` : undefined} />;
}
