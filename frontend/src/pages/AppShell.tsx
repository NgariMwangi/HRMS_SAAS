import { ReactNode, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

export default function AppShell({
  brandLabel,
  nav,
  onSignOut,
  children,
}: {
  brandLabel: string;
  nav: ReactNode;
  onSignOut: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  return (
    <div className={`shell${open ? " nav-open" : ""}`}>
      <header className="topbar">
        <button className="menu-btn" type="button" aria-label="Open menu" onClick={() => setOpen(true)}>
          <span />
          <span />
          <span />
        </button>
        <div className="rail-brand">
          <span className="mark">H</span>
          <div>
            <strong>HRMS</strong>
            <span>{brandLabel}</span>
          </div>
        </div>
      </header>
      <button className="rail-backdrop" type="button" aria-label="Close menu" onClick={() => setOpen(false)} />
      <aside className="rail">
        <div className="rail-brand">
          <span className="mark">H</span>
          <div>
            <strong>HRMS</strong>
            <span>{brandLabel}</span>
          </div>
        </div>
        <nav>{nav}</nav>
        <button className="rail-signout" type="button" onClick={onSignOut}>
          Sign out
        </button>
      </aside>
      <div className="content">
        <div className="content-inner">{children}</div>
      </div>
    </div>
  );
}
