import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { adminToken } from "./api";

export default function AdminShell() {
  const navigate = useNavigate();
  if (!adminToken.get()) {
    navigate("/admin/login", { replace: true });
    return null;
  }

  return (
    <div className="admin-shell">
      <aside>
        <p className="brand">HRMS</p>
        <p className="brand-sub">Platform</p>
        <nav>
          <NavLink to="/admin" end>
            Overview
          </NavLink>
          <NavLink to="/admin/tenants">Tenants</NavLink>
          <NavLink to="/admin/countries">Countries</NavLink>
        </nav>
        <button
          className="ghost sidebar-out"
          type="button"
          onClick={() => {
            adminToken.clear();
            navigate("/admin/login");
          }}
        >
          Sign out
        </button>
      </aside>
      <div className="admin-main">
        <Outlet />
      </div>
    </div>
  );
}
