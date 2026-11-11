import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../api";
import type { Notice } from "../components/performanceTypes";
import { performancePages, appraisalNoticePath } from "../performanceNavigation";
import { recruitmentPages } from "../recruitmentNavigation";
import { generalReports } from "../reportNavigation";
import { canVisit } from "../access";
import { useSidebarMin } from "../hooks/useSidebarMin";
import {
  IconBell,
  IconBriefcase,
  IconBuilding,
  IconCalendar,
  IconChart,
  IconCheck,
  IconChevron,
  IconClock,
  IconCollapse,
  IconDoc,
  IconDownload,
  IconHelp,
  IconHome,
  IconLogout,
  IconPay,
  IconPeople,
  IconPlug,
  IconSearch,
  IconSettings,
  IconTarget,
} from "../components/icons";
import OfflineBanner from "../components/OfflineBanner";
import { ThemeToggle } from "../theme";
import { Avatar } from "../ui";
import { useInstallPrompt } from "../pwa";


type NavItem = { to: string; label: string; icon?: ReactNode; end?: boolean };
type NavGroup = { id: string; label?: string; items: NavItem[] };

const groups: NavGroup[] = [
  { id: "home", items: [{ to: "/app", label: "Overview", icon: <IconHome />, end: true }] },
  {
    id: "people",
    label: "People",
    items: [
      { to: "/app/people", label: "Employees", icon: <IconPeople /> },
      { to: "/app/departments", label: "Departments", icon: <IconBuilding /> },
      { to: "/app/job-titles", label: "Job titles", icon: <IconBriefcase /> },
      { to: "/app/documents", label: "Documents", icon: <IconDoc /> },
      { to: "/app/lifecycle", label: "Lifecycle", icon: <IconClock /> },
    ],
  },
  {
    id: "time",
    label: "Attendance & leave",
    items: [
      { to: "/app/attendance", label: "Attendance", icon: <IconCalendar /> },
      { to: "/app/leave", label: "Leave", icon: <IconCheck /> },
    ],
  },
  {
    id: "pay",
    label: "Payroll",
    items: [
      { to: "/app/payroll", label: "Payroll", icon: <IconPay /> },
      { to: "/app/payroll/settings", label: "Pay configuration", icon: <IconSettings /> },
      { to: "/app/payroll/consultants", label: "Consultants", icon: <IconBriefcase /> },
      { to: "/app/payroll/overtime", label: "Overtime", icon: <IconClock /> },
      { to: "/app/payroll/payments", label: "Payment history", icon: <IconPay /> },
      { to: "/app/payroll/imported-history", label: "Imported history", icon: <IconDoc /> },
    ],
  },
  {
    id: "performance", label: "Performance",
    items: performancePages.filter(page => !["rating-scales", "competencies", "calibration"].includes(page.path)).map(page => ({
      to: `/app/performance/${page.path}`, label: page.label,
      icon: page.path === "reports" ? <IconChart /> : page.path === "templates" ? <IconSettings /> : page.path === "team" ? <IconPeople /> : <IconTarget />,
    })),
  },
  {
    id: "recruitment", label: "Recruitment",
    items: recruitmentPages.map(page => ({ to: `/app/recruitment/${page.path}`, label: page.label, icon: page.path === "reports" ? <IconChart /> : page.path === "candidates" ? <IconPeople /> : page.path === "interviews" ? <IconCalendar /> : page.path === "offers" ? <IconDoc /> : <IconBriefcase /> })),
  },
  {
    id: "reports",
    label: "Reports",
    items: [
      { to: "/app/reports", label: "All reports", icon: <IconChart />, end: true },
      ...generalReports.map(report => ({ to: `/app/reports/${report.key}`, label: report.title, icon: <IconChart /> })),
    ],
  },
  {
    id: "settings",
    label: "Settings",
    items: [
      { to: "/app/settings", label: "Workspace", icon: <IconSettings /> },
      { to: "/app/companies", label: "Companies", icon: <IconBuilding /> },
      { to: "/app/branches", label: "Branches", icon: <IconBuilding /> },
      { to: "/app/integrations", label: "Integrations", icon: <IconPlug /> },
    ],
  },
];

const titles: Record<string, string> = {
  "/app": "Overview",
  "/app/people": "Employees",
  "/app/people/new": "Add employee",
  "/app/departments": "Departments",
  "/app/job-titles": "Job titles",
  "/app/companies": "Companies",
  "/app/branches": "Branches",
  "/app/documents": "Documents",
  "/app/lifecycle": "Employee lifecycle",
  "/app/attendance": "Attendance",
  "/app/leave": "Leave",
  "/app/payroll": "Payroll",
  "/app/payroll/settings": "Payroll settings",
  "/app/performance": "Performance",
  "/app/recruitment": "Recruitment",
  "/app/reports": "Reports",
  "/app/integrations": "Integrations",
  "/app/settings": "Workspace",
};

export default function TenantShell() {
  const { user, tenant, company, branch, companies, branches, setCompanyId, setBranchId, signOut, hasPermission } = useWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const { minimized, toggle } = useSidebarMin();
  const [open, setOpen] = useState(false);
  const [groupsCollapsed, setGroupsCollapsed] = useState<Record<string, boolean>>({});
  const [switcher, setSwitcher] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [notices, setNotices] = useState<Notice[]>([]);
  const canSeePerformance = canVisit("/app/performance", hasPermission);
  useEffect(() => {
    let active = true;
    setNotices([]);
    const refreshNotices = () => {
      if (!company || !canSeePerformance) return;
      void api<Notice[]>(`/performance/notifications?company_id=${company.id}`).then(rows => { if (active) setNotices(rows.filter(row => !row.read_at)); }).catch(() => { if (active) setNotices([]); });
    };
    refreshNotices();
    window.addEventListener("focus", refreshNotices);
    return () => { active = false; window.removeEventListener("focus", refreshNotices); };
  }, [company?.id, location.pathname, location.search, notifyOpen, canSeePerformance]);
  const [query, setQuery] = useState("");
  const [iosHint, setIosHint] = useState(false);
  const { canInstall, showIosHint, install } = useInstallPrompt();

  useEffect(() => {
    setOpen(false);
    setSwitcher(false);
    setUserMenu(false);
    setNotifyOpen(false);
    if (location.pathname.startsWith("/app/performance")) setGroupsCollapsed(current => ({ ...current, performance: false }));
    if (location.pathname.startsWith("/app/recruitment")) setGroupsCollapsed(current => ({ ...current, recruitment: false }));
    if (location.pathname.startsWith("/app/reports")) setGroupsCollapsed(current => ({ ...current, reports: false }));
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    setIosHint(showIosHint && sessionStorage.getItem("hrms-ios-install") !== "1");
  }, [showIosHint]);

  const pageTitle = useMemo(() => {
    if (location.pathname.endsWith("/edit") && location.pathname.startsWith("/app/people/")) return "Edit employee";
    if (location.pathname.endsWith("/documents") && location.pathname.startsWith("/app/people/")) return "Employee documents";
    if (location.pathname.endsWith("/salary") && location.pathname.startsWith("/app/people/")) return "Salary";
    if (location.pathname.startsWith("/app/people/") && location.pathname !== "/app/people/new") return "Employee";
    if (location.pathname.startsWith("/app/performance/appraisals/")) return "Employee review";
    if (location.pathname.startsWith("/app/performance/reviews/")) return "Review setup";
    const performancePage = performancePages.find(page => location.pathname === `/app/performance/${page.path}`);
    const recruitmentPage = recruitmentPages.find(page => location.pathname.startsWith(`/app/recruitment/${page.path}`));
    const report = generalReports.find(report => location.pathname === `/app/reports/${report.key}`);
    return report?.title ?? performancePage?.title ?? (recruitmentPage ? `Recruitment · ${recruitmentPage.label}` : undefined) ?? titles[location.pathname] ?? "HRMS";
  }, [location.pathname]);

  function onSearch(event: FormEvent) {
    event.preventDefault();
    navigate(`/app/people?q=${encodeURIComponent(query.trim())}`);
  }

  function pickCompany(id: string) {
    setCompanyId(id);
    setSwitcher(false);
    setOpen(false);
  }

  function pickBranch(id: string) {
    setBranchId(id);
    setSwitcher(false);
    setOpen(false);
  }

  return (
    <div className={`app${open ? " nav-open" : ""}${minimized ? " rail-min" : ""}`}>
      <button className="rail-backdrop" type="button" aria-label="Close menu" onClick={() => setOpen(false)} />
      <aside className="sidebar">
        <div className="sidebar-head">
          <div className="brand-row">
            <span className="mark">H</span>
            <span>HRMS</span>
            <button
              className="rail-toggle"
              type="button"
              onClick={toggle}
              title={minimized ? "Expand sidebar" : "Minimize sidebar"}
              aria-label={minimized ? "Expand sidebar" : "Minimize sidebar"}
            >
              <IconCollapse />
            </button>
          </div>
          <div style={{ position: "relative" }}>
            <button className={`switcher${switcher ? " open" : ""}`} type="button" onClick={() => setSwitcher((value) => !value)} aria-expanded={switcher}>
              <Avatar name={company?.name ?? tenant?.name ?? "Company"} size="sm" />
              <div style={{ minWidth: 0, flex: 1 }}>
                <strong>{company?.name ?? tenant?.name ?? "Workspace"}</strong>
                <span>{branch ? `${branch.name} · ${branch.code}` : "Select a branch"}</span>
              </div>
              <IconChevron />
            </button>
            {switcher ? (
              <div className="switcher-menu" style={{ left: 0, right: 0, top: "calc(100% + 6px)" }}>
                <div className="menu-label">Companies</div>
                {companies.map((row) => (
                  <button
                    key={row.id}
                    className={`menu-item${row.id === company?.id ? " active" : ""}`}
                    type="button"
                    onClick={() => pickCompany(row.id)}
                  >
                    {row.name}
                  </button>
                ))}
                <div className="menu-label">Branches</div>
                {branches.length === 0 ? <div className="menu-item">No branches</div> : null}
                {branches.map((row) => (
                  <button
                    key={row.id}
                    className={`menu-item${row.id === branch?.id ? " active" : ""}`}
                    type="button"
                    onClick={() => pickBranch(row.id)}
                  >
                    {row.name} · {row.code}
                  </button>
                ))}
                {hasPermission("organization.manage") ? <><NavLink className="menu-item" to="/app/companies">Manage companies</NavLink><NavLink className="menu-item" to="/app/branches">Manage branches</NavLink></> : null}
              </div>
            ) : null}
          </div>
        </div>
        <nav className="nav-scroll">
          {groups.map((group) => {
            const items = group.items.filter((item) => canVisit(item.to, hasPermission) && (item.to !== "/app/performance/my" || user.employee_id));
            if (items.length === 0) return null;
            const collapsed = Boolean(groupsCollapsed[group.id]);
            return (
            <div key={group.id}>
              {group.label ? (
                <button
                  className={`nav-group-label${collapsed ? "" : " open"}`}
                  type="button"
                  aria-expanded={!collapsed}
                  onClick={() => setGroupsCollapsed((current) => ({ ...current, [group.id]: !current[group.id] }))}
                >
                  {group.label}
                  <IconChevron />
                </button>
              ) : null}
              {collapsed && !minimized ? null : (
                <>
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      title={item.label}
                      className={({ isActive }) => `nav-link${isActive || item.to === "/app/performance/settings" && ["/app/performance/rating-scales", "/app/performance/competencies", "/app/performance/calibration"].includes(location.pathname) ? " active" : ""}`}
                    >
                      {item.icon}
                      <span className="nav-label">{item.label}</span>
                    </NavLink>
                  ))}
                </>
              )}
            </div>
            );
          })}
        </nav>
        <div className="sidebar-foot" style={{ position: "relative" }}>
          <button className="user-chip" type="button" onClick={() => setUserMenu((value) => !value)}>
            <Avatar name={user.full_name} />
            <div>
              <strong>{user.full_name}</strong>
              <span>{user.role.toLowerCase()}</span>
            </div>
          </button>
          {userMenu ? (
            <div className="menu-pop" style={{ left: 12, right: 12, bottom: "calc(100% + 8px)" }}>
              {canVisit("/app/settings", hasPermission) ? <NavLink className="menu-item" to="/app/settings">Settings</NavLink> : null}
              {canInstall ? (
                <button className="menu-item" type="button" onClick={() => void install()}>
                  <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><IconDownload /> Install app</span>
                </button>
              ) : null}
              {user.employee_id && <Link className="menu-item" to="/employee" onClick={() => setUserMenu(false)}>Employee portal</Link>}
              <button className="menu-item" type="button" onClick={signOut}>
                <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><IconLogout /> Sign out</span>
              </button>
            </div>
          ) : null}
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <button className="menu-btn" type="button" aria-label="Open menu" onClick={() => setOpen(true)}>
            <span /><span /><span />
          </button>
          <div className="crumbs">
            <span>{company?.name ?? "Workspace"}</span>
            <span>/</span>
            <strong>{pageTitle}</strong>
          </div>
          <form className="topbar-search" onSubmit={onSearch}>
            <IconSearch />
            <input
              placeholder="Search people, payroll, settings"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
          <div className="topbar-actions">
            {canInstall ? (
              <button className="btn ghost small" type="button" onClick={() => void install()}>
                <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><IconDownload /> Install</span>
              </button>
            ) : null}
            <ThemeToggle />
            <div style={{ position: "relative" }}>
              <button className="icon-btn" type="button" aria-label="Notifications" onClick={() => setNotifyOpen((value) => !value)}>
                <IconBell />
                {notices.length > 0 ? <span className="dot" /> : null}
              </button>
              {notifyOpen ? (
                <div className="notify-pop" style={{ right: 0, top: "calc(100% + 8px)" }}>
                  <div className="menu-label">Notifications</div>
                  {notices.length === 0 ? (
                    <div className="menu-item">No notifications for this workspace</div>
                  ) : (
                    notices.map((item) => (
                        <button key={item.id} className="menu-item" onClick={() => { setNotifyOpen(false); void api(`/performance/notifications/${item.id}/read`, { method: "POST" }).then(() => setNotices(rows => rows.filter(row => row.id !== item.id))).catch(() => undefined); navigate(appraisalNoticePath(item)); }}>
                          <strong style={{ display: "block", fontSize: 13 }}>{item.message}</strong>
                          <span className="muted">{new Date(item.created_at + "Z").toLocaleDateString()}</span>
                        </button>
                    ))
                  )}
                </div>
              ) : null}
            </div>
            <button className="icon-btn" type="button" aria-label="Help" title="Help">
              <IconHelp />
            </button>
          </div>
        </header>
        <main className="content">
          <div className="content-inner">
            <OfflineBanner />
            {iosHint ? (
              <div className="install-hint" role="note">
                <span>On iPhone, tap Share, then Add to Home Screen to install this workspace.</span>
                <button
                  className="btn ghost small"
                  type="button"
                  onClick={() => {
                    sessionStorage.setItem("hrms-ios-install", "1");
                    setIosHint(false);
                  }}
                >
                  Dismiss
                </button>
              </div>
            ) : null}
            {canVisit(location.pathname, hasPermission) ? <Outlet /> : <section className="card card-pad"><h2>Access restricted</h2><p className="muted">Your role does not allow access to this page.</p></section>}
          </div>
        </main>
      </div>
    </div>
  );
}
