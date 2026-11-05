import { Navigate } from "react-router-dom";

// Preserve existing employee login links while using one company sign-in page.
export default function EmployeeLogin() {
  return <Navigate to="/" replace />;
}
