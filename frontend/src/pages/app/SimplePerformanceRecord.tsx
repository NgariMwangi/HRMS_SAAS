import { useNavigate, useParams } from "react-router-dom";
import AppraisalRecord from "../../components/AppraisalRecord";
import { useWorkspace } from "../../context/WorkspaceContext";
export default function SimplePerformanceRecord() {
  const { recordId } = useParams(); const navigate = useNavigate(); const { hasPermission: has, company } = useWorkspace();
  return recordId ? <AppraisalRecord key={`${company?.id}:${recordId}`} identity={recordId} back={() => navigate(`/app/performance/${has("performance.manage_cycles") ? "reviews" : has("performance.view_team") ? "team" : "my"}`)} /> : <p>Appraisal not found.</p>;
}
