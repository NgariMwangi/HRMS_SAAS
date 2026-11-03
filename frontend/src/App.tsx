import { CompanyDomainProvider } from "./context/CompanyDomainContext";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { lazy, Suspense } from "react";
import { PageSkeleton } from "./ui";
import { WorkspaceProvider, useWorkspace } from "./context/WorkspaceContext";
import TenantShell from "./layouts/TenantShell";
import AdminAuditLogs from "./pages/AdminAuditLogs";
import AdminCountries from "./pages/AdminCountries";
import AdminPayrollPacks from "./pages/AdminPayrollPacks";
import AdminEmployeeProfile from "./pages/AdminEmployeeProfile";
import AdminEmployeeSalary from "./pages/AdminEmployeeSalary";
import AdminLogin from "./pages/AdminLogin";
import AdminOverview from "./pages/AdminOverview";
import AdminShell from "./pages/AdminShell";
import AdminTenantDetail from "./pages/AdminTenantDetail";
import AdminTenants from "./pages/AdminTenants";
import AttendancePage from "./pages/app/Attendance";
import BranchesPage from "./pages/app/Branches";
import CompaniesPage from "./pages/app/Companies";
import Dashboard from "./pages/app/Dashboard";
import DepartmentsPage from "./pages/app/Departments";
import DocumentsPage from "./pages/app/Documents";
import EmployeeCreate from "./pages/app/EmployeeCreate";
import EmployeeDocumentsPage from "./pages/app/EmployeeDocumentsPage";
import EmployeeProfile from "./pages/app/EmployeeProfile";
import EmployeeSalaryPage from "./pages/app/EmployeeSalary";
import EmployeesPage from "./pages/app/Employees";
import IntegrationsPage from "./pages/app/Integrations";
import JobTitlesPage from "./pages/app/JobTitles";
import LeavePage from "./pages/app/Leave";
import LifecyclePage from "./pages/app/Lifecycle";
import PayrollPage from "./pages/app/Payroll";
import PayrollSettingsPage from "./pages/app/PayrollSettings";
const RecruitmentPage = lazy(() => import("./pages/app/Recruitment"));
const ReportsPage = lazy(() => import("./pages/app/Reports"));
import SettingsPage from "./pages/app/Settings";
import TenantAuth from "./pages/TenantAuth";
import EmployeeLogin from "./pages/EmployeeLogin";
const EmployeePortal = lazy(() => import("./pages/EmployeePortal"));
const PerformanceRecord = lazy(() => import("./pages/app/PerformanceRecord"));
const SimplePerformanceRecord = lazy(() => import("./pages/app/SimplePerformanceRecord"));
const PerformancePage = lazy(() => import("./pages/app/Performance"));

function TenantApp() {
  return (
    <WorkspaceProvider>
      <WorkspaceEntry />
    </WorkspaceProvider>
  );
}

function WorkspaceEntry() {
  const { user } = useWorkspace();
  const location = useLocation();
  if (user.role !== "EMPLOYEE") return <TenantShell />;
  const segment = location.pathname.split("/")[2] ?? "";
  const linkedSection = location.pathname.split("/")[5] ?? "goals";
  const linkedAppraisal = location.pathname.match(/^\/app\/performance\/appraisals\/([^/]+)/)?.[1];
  const linkedRecord = location.pathname.match(/^\/app\/performance\/records\/([^/]+)/)?.[1];
  const target = segment === "people" ? "profile" : ["leave", "attendance", "documents", "performance", "settings"].includes(segment) ? segment === "settings" ? "account" : segment : "";
  return <Navigate to={`/employee${target ? `/${target}` : ""}${linkedRecord ? `?record=${encodeURIComponent(linkedRecord)}` : linkedAppraisal ? `?appraisal=${encodeURIComponent(linkedAppraisal)}&section=${encodeURIComponent(linkedSection)}` : location.search}`} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <CompanyDomainProvider>
      <Routes>
        <Route path="/" element={<TenantAuth />} />
        <Route path="/employee/login" element={<EmployeeLogin />} />
        <Route path="/employee/:section?" element={<WorkspaceProvider employeePortal><Suspense fallback={<PageSkeleton />}><EmployeePortal /></Suspense></WorkspaceProvider>} />
        <Route path="/workspace" element={<Navigate to="/app" replace />} />
        <Route path="/app" element={<TenantApp />}>
          <Route index element={<Dashboard />} />
          <Route path="people" element={<EmployeesPage />} />
          <Route path="people/new" element={<EmployeeCreate />} />
          <Route path="people/:employeeId/edit" element={<EmployeeCreate />} />
          <Route path="people/:employeeId/documents" element={<EmployeeDocumentsPage />} />
          <Route path="people/:employeeId/salary" element={<EmployeeSalaryPage />} />
          <Route path="people/:employeeId" element={<EmployeeProfile />} />
          <Route path="departments" element={<DepartmentsPage />} />
          <Route path="job-titles" element={<JobTitlesPage />} />
          <Route path="companies" element={<CompaniesPage />} />
          <Route path="branches" element={<BranchesPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="lifecycle" element={<LifecyclePage />} />
          <Route path="attendance" element={<AttendancePage />} />
          <Route path="leave" element={<LeavePage />} />
          <Route path="payroll" element={<PayrollPage />} />
          <Route path="payroll/settings" element={<PayrollSettingsPage />} />
          <Route path="performance/appraisals/:appraisalId/:section?" element={<Suspense fallback={<PageSkeleton />}><PerformanceRecord /></Suspense>} />
          <Route path="performance/records/:recordId" element={<Suspense fallback={<PageSkeleton />}><SimplePerformanceRecord /></Suspense>} />
          <Route path="performance/:page" element={<Suspense fallback={<PageSkeleton />}><PerformancePage /></Suspense>} />
          <Route path="performance" element={<Suspense fallback={<PageSkeleton />}><PerformancePage /></Suspense>} />
          <Route path="recruitment" element={<Suspense fallback={<PageSkeleton />}><RecruitmentPage /></Suspense>} />
          <Route path="recruitment/:page/:identity?" element={<Suspense fallback={<PageSkeleton />}><RecruitmentPage /></Suspense>} />
          <Route path="reports" element={<Suspense fallback={<PageSkeleton />}><ReportsPage /></Suspense>} />
          <Route path="reports/:report" element={<Suspense fallback={<PageSkeleton />}><ReportsPage /></Suspense>} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<AdminOverview />} />
          <Route path="tenants" element={<AdminTenants />} />
          <Route path="tenants/:tenantId" element={<AdminTenantDetail />} />
          <Route path="tenants/:tenantId/employees/:employeeId/salary" element={<AdminEmployeeSalary />} />
          <Route path="tenants/:tenantId/employees/:employeeId" element={<AdminEmployeeProfile />} />
          <Route path="countries" element={<AdminCountries />} />
          <Route path="countries/:countryId/packs" element={<AdminPayrollPacks />} />
          <Route path="audit-logs" element={<AdminAuditLogs />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </CompanyDomainProvider>
    </BrowserRouter>
  );
}
