import { useNavigate, useParams } from "react-router-dom";
import LegacyAppraisal from "../../components/LegacyAppraisal";
export default function PerformanceRecord() {
  const { appraisalId } = useParams(); const navigate = useNavigate();
  return appraisalId ? <LegacyAppraisal key={appraisalId} identity={appraisalId} back={() => navigate("/app/performance/archive")} /> : <p>Appraisal not found.</p>;
}
