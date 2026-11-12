import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../api";
import { PageSkeleton } from "../ui";
import { CompanyTheme } from "../components/CompanyBranding";

type DomainContext = { company: { company_id: string; tenant_id: string; company_name: string; hostname: string; scope?: "company" | "workspace"; theme_color?: string; logo_data_url?: string | null } | null; central_url: string };
const Context = createContext<DomainContext>({ company: null, central_url: "" });

export function CompanyDomainProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<DomainContext | null>(null);
  const [error, setError] = useState("");
  const location = useLocation();
  useEffect(() => {
    let active = true;
    api<DomainContext>("/domains/context").then(data => { if (active) setValue(data); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, []);
  if (error) return <main className="content"><section className="card card-pad"><h1>Unable to open this workspace</h1><p className="error">{error}</p><button className="btn" onClick={() => window.location.reload()}>Try again</button></section></main>;
  if (!value) return <PageSkeleton />;
  if (value.company && location.pathname.startsWith("/admin")) return <main className="content"><section className="card card-pad"><h1>Platform administration</h1><p>Open the main HRMS address to manage the platform.</p><a className="btn" href={`${value.central_url}/admin`}>Open Platform Admin</a></section></main>;
  return <Context.Provider value={value}><CompanyTheme company={value.company} />{children}</Context.Provider>;
}

export const useCompanyDomain = () => useContext(Context);
