import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { adminSession, adminToken, api } from "../api";
import { useSidebarMin } from "../hooks/useSidebarMin";
import {
  IconBell,
  IconBuilding,
  IconClock,
  IconCollapse,
  IconHelp,
  IconHome,
  IconLogout,
  IconPeople,
  IconSearch,
} from "../components/icons";
import type { PlatformAuth } from "../types";
import { ThemeToggle } from "../theme";
import { Avatar } from "../ui";

const titles: Record<string, string> = {
  "/admin": "Overview",
  "/admin/tenants": "Tenants",
  "/admin/countries": "Countries",
  "/admin/audit-logs": "Audit log",
};

const tenantModules = [
  ["overview", "Tenant overview"], ["companies", "Companies"], ["branches", "Branches"], ["employees", "People"],
  ["users", "Portal accounts"], ["access", "Roles & permissions"], ["attendance", "Attendance"], ["leave", "Leave"],
  ["payroll", "Payroll"], ["lifecycle", "Employee lifecycle"], ["documents", "Documents"],
  ["performance", "Performance"], ["recruitment", "Recruitment"], ["reports", "Reports"], ["domains", "Company domains"],
];

export default function AdminShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const stored = adminSession.get();
  const [admin, setAdmin] = useState(stored);
  const { minimized, toggle } = useSidebarMin();
  const [open, setOpen] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setOpen(false);
    setUserMenu(false);
    setNotifyOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    const token = adminToken.get();
    if (!token) {
      navigate("/admin/login", { replace: true });
      return;
    }
    api<PlatformAuth["admin"]>("/platform/me", { token })
      .then((profile) => {
        setAdmin(profile);
        adminSession.set(profile);
      })
      .catch(() => {
        adminToken.clear();
        adminSession.clear();
        navigate("/admin/login", { replace: true });
      });
  }, [navigate]);

  const selectedTenant = location.pathname.match(/^\/admin\/tenants\/([^/]+)/)?.[1];
  const selectedTab = new URLSearchParams(location.search).get("tab") || "overview";
  const pageTitle = useMemo(() => {
    if (location.pathname.includes("/packs")) return "Payroll packs";
    if (location.pathname.includes("/salary")) return "Salary";
    if (location.pathname.includes("/employees/")) return "Employee";
    if (location.pathname.startsWith("/admin/tenants/") && location.pathname !== "/admin/tenants") {
      return tenantModules.find(([id]) => id === selectedTab)?.[1] || "Tenant";
    }
    return titles[location.pathname] ?? "Console";
  }, [location.pathname, selectedTab]);

  function signOut() {
    adminToken.clear();
    adminSession.clear();
    navigate("/admin/login");
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    navigate(`/admin/tenants?q=${encodeURIComponent(query.trim())}`);
  }

  const displayName = admin?.full_name ?? "Platform owner";

  return (
    <div className={`app${open ? " nav-open" : ""}${minimized ? " rail-min" : ""}`}>
      <button className="rail-backdrop" type="button" aria-label="Close menu" onClick={() => setOpen(false)} />
      <aside className="sidebar">
        <div className="sidebar-head compact">
          <div className="brand-row">
            <span className="mark">H</span>
            <div>
              <span>HRMS</span>
              <small>Platform</small>
            </div>
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
        </div>
        <nav className="nav-scroll">
          <NavLink to="/admin" end title="Overview" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <IconHome /> <span className="nav-label">Overview</span>
          </NavLink>
          <NavLink to="/admin/tenants" title="Tenants" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <IconPeople /> <span className="nav-label">Tenants</span>
          </NavLink>
          <NavLink to="/admin/countries" title="Countries" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <IconBuilding /> <span className="nav-label">Countries</span>
          </NavLink>
          <NavLink to="/admin/audit-logs" title="Audit log" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            <IconClock /> <span className="nav-label">Audit log</span>
          </NavLink>
          {selectedTenant && <div className="portal-admin-nav"><span className="menu-label">Selected tenant</span>{tenantModules.map(([tab, title]) => <Link key={tab} to={`/admin/tenants/${selectedTenant}?tab=${tab}`} title={title} className={`nav-link${!location.pathname.includes("/employees/") && selectedTab === tab ? " active" : ""}`} aria-current={!location.pathname.includes("/employees/") && selectedTab === tab ? "page" : undefined}><IconBuilding /><span className="nav-label">{title}</span></Link>)}</div>}
        </nav>
        <div className="sidebar-foot" style={{ position: "relative" }}>
          <button className="user-chip" type="button" onClick={() => setUserMenu((value) => !value)}>
            <Avatar name={displayName} />
            <div>
              <strong>{displayName}</strong>
              <span>owner</span>
            </div>
          </button>
          {userMenu ? (
            <div className="menu-pop" style={{ left: 12, right: 12, bottom: "calc(100% + 8px)" }}>
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
            <span>Platform</span>
            <span>/</span>
            <strong>{pageTitle}</strong>
          </div>
          <form className="topbar-search" onSubmit={onSearch}>
            <IconSearch />
            <input
              placeholder="Search tenants"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
          <div className="topbar-actions">
            <ThemeToggle />
            <div style={{ position: "relative" }}>
              <button className="icon-btn" type="button" aria-label="Platform activity" onClick={() => setNotifyOpen((value) => !value)}>
                <IconBell />
              </button>
              {notifyOpen ? (
                <div className="notify-pop" style={{ right: 0, top: "calc(100% + 8px)" }}>
                  <div className="menu-label">Platform activity</div>
                  <p className="muted" style={{ padding: "0 16px" }}>View recorded platform and tenant activity in the audit log.</p><Link className="menu-item" to="/admin/audit-logs">Open audit log</Link>
                </div>
              ) : null}
            </div>
            <Link className="icon-btn" to="/admin/tenants" aria-label="Select a tenant to open its modules" title="Select a tenant to open its modules"><IconHelp /></Link>
          </div>
        </header>
        <main className="content">
          <div className="content-inner">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
