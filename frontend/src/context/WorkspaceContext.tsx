import { useCompanyDomain } from "./CompanyDomainContext";
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, tenantSession, tenantToken } from "../api";
import { clearPwaCaches } from "../pwa";
import type { Branch, Company, MyAccess, Tenant, User } from "../types";
import { KpiRowSkeleton, Skel, TableSkeleton } from "../ui";

type OrgSelect = { companyId?: string; branchId?: string };

type WorkspaceValue = {
  token: string;
  user: User;
  tenant: Tenant | null;
  companies: Company[];
  allBranches: Branch[];
  branches: Branch[];
  company: Company | null;
  branch: Branch | null;
  canManageOrg: boolean;
  hasPermission: (permission: string) => boolean;
  reloadAccess: () => Promise<MyAccess>;
  setCompanyId: (id: string) => void;
  setBranchId: (id: string) => void;
  reloadOrg: (select?: OrgSelect) => Promise<void>;
  signOut: () => void;
  toast: string | null;
  notify: (message: string) => void;
};

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

function pickIds(
  companyRows: Company[],
  branchRows: Branch[],
  currentCompanyId: string,
  currentBranchId: string,
  select?: OrgSelect,
): { companyId: string; branchId: string } {
  const companyId =
    select?.companyId && companyRows.some((row) => row.id === select.companyId)
      ? select.companyId
      : companyRows.some((row) => row.id === currentCompanyId)
        ? currentCompanyId
        : companyRows[0]?.id ?? "";
  const companyBranches = branchRows.filter((row) => row.company_id === companyId);
  const branchId =
    select?.branchId && companyBranches.some((row) => row.id === select.branchId)
      ? select.branchId
      : companyBranches.some((row) => row.id === currentBranchId)
        ? currentBranchId
        : companyBranches[0]?.id ?? "";
  return { companyId, branchId };
}

export function WorkspaceProvider({ children, employeePortal = false }: { children: ReactNode; employeePortal?: boolean }) {
  const { company: domainCompany } = useCompanyDomain();
  const navigate = useNavigate();
  const location = useLocation();
  const token = tenantToken.get();
  const session = tenantSession.get();
  const [user, setUser] = useState<User | null>(session?.user ?? null);
  const [tenant] = useState<Tenant | null>(session?.tenant ?? null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [allBranches, setAllBranches] = useState<Branch[]>([]);
  const [companyId, setCompanyId] = useState(session?.companyId ?? "");
  const [branchId, setBranchId] = useState(session?.branchId ?? "");
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const idsRef = useRef({ companyId, branchId });
  idsRef.current = { companyId, branchId };

  const reloadAccess = useCallback(async () => {
    const [me, access] = await Promise.all([api<User>("/auth/me"), api<MyAccess>("/access/me")]);
    setUser(me);
    setPermissions(access.permissions);
    tenantSession.patch({ user: me });
    return access;
  }, []);

  const accessReady = permissions !== null;
  useEffect(() => {
    if (!token || !accessReady) return;
    const refresh = () => { void reloadAccess().catch((err: Error) => setError(err.message)); };
    refresh();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [location.pathname, token, accessReady, reloadAccess]);

  const reloadOrg = useCallback(async (select?: OrgSelect) => {
    const currentToken = tenantToken.get();
    if (!currentToken) return;
    const [companyRows, branchRows] = await Promise.all([
      api<Company[]>("/companies", { token: currentToken }),
      api<Branch[]>("/branches", { token: currentToken }),
    ]);
    const next = pickIds(
      companyRows,
      branchRows,
      idsRef.current.companyId,
      idsRef.current.branchId,
      select,
    );
    setCompanies(companyRows);
    setAllBranches(branchRows);
    setCompanyId(next.companyId);
    setBranchId(next.branchId);
    tenantSession.patch({ companyId: next.companyId, branchId: next.branchId });
  }, []);

  useEffect(() => {
    if (!token) {
      navigate(employeePortal ? "/employee/login" : "/");
      return;
    }
    Promise.all([
      api<User>("/auth/me", { token }),
      api<Company[]>("/companies", { token }),
      api<Branch[]>("/branches", { token }),
      api<MyAccess>("/access/me", { token }),
    ])
      .then(([me, companyRows, branchRows, access]) => {
        setUser(me);
        setPermissions(access.permissions);
        setCompanies(companyRows);
        setAllBranches(branchRows);
        const next = pickIds(companyRows, branchRows, companyId, branchId);
        setCompanyId(next.companyId);
        setBranchId(next.branchId);
        if (session) {
          tenantSession.set({ ...session, user: me, companyId: next.companyId, branchId: next.branchId });
        }
      })
      .catch((err: Error) => {
        setError(err.message);
        if (err.message.toLowerCase().includes("token") || err.message.toLowerCase().includes("authenticated")) {
          tenantToken.clear();
          tenantSession.clear();
          navigate(employeePortal ? "/employee/login" : "/");
        }
      });
  }, [navigate, token]);

  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 2800);
  }

  const value = useMemo<WorkspaceValue | null>(() => {
    if (!user || !token || permissions === null) return null;
    const company = companies.find((row) => row.id === companyId) ?? companies[0] ?? null;
    const companyBranches = allBranches.filter((row) => row.company_id === company?.id);
    const branch = companyBranches.find((row) => row.id === branchId) ?? companyBranches[0] ?? null;
    return {
      token,
      user,
      tenant,
      companies,
      allBranches,
      branches: companyBranches,
      company,
      branch,
      canManageOrg: permissions.includes("organization.manage"),
      hasPermission: (permission) => permissions.includes(permission) && (!employeePortal || permission.endsWith(".view_own") || ["attendance.self", "people.update_own_contact", "performance.manage_own_goals", "performance.self_assess", "recruitment.interview"].includes(permission)),
      reloadAccess,
      setCompanyId: (id: string) => {
        if (domainCompany && id !== domainCompany.company_id) return;
        setCompanyId(id);
        const first = allBranches.find((row) => row.company_id === id);
        setBranchId(first?.id ?? "");
        tenantSession.patch({ companyId: id, branchId: first?.id });
      },
      setBranchId: (id: string) => {
        setBranchId(id);
        tenantSession.patch({ branchId: id });
      },
      reloadOrg,
      signOut: () => {
        tenantToken.clear();
        tenantSession.clear();
        void clearPwaCaches();
        navigate(employeePortal ? "/employee/login" : "/");
      },
      toast,
      notify,
    };
  }, [user, token, tenant, companies, allBranches, companyId, branchId, toast, navigate, reloadOrg, permissions, reloadAccess, employeePortal, domainCompany]);

  if (!token) return null;
  if (!value) {
    return (
      <div className="content" aria-busy="true">
        <div className="content-inner">
          <Skel w={220} h={22} />
          <div style={{ marginTop: 18 }}><KpiRowSkeleton /></div>
          <section className="card">
            <TableSkeleton rows={4} cols={3} />
          </section>
          {error ? <p className="muted">{error}</p> : null}
        </div>
      </div>
    );
  }

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
      {toast ? <div className="toast">{toast}</div> : null}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return value;
}
