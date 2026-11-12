import { useCompanyDomain } from "../context/CompanyDomainContext";
import { ReactNode } from "react";
import { ThemeToggle } from "../theme";
import { CompanyLogo } from "../components/CompanyBranding";

export default function AuthLayout({
  children,
  kicker = "People operations for growing companies",
}: {
  children: ReactNode;
  kicker?: string;
}) {
  const { company } = useCompanyDomain();
  return (
    <div className="auth-screen">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      <aside className="auth-aside">
        <div className="brand-row">
          <CompanyLogo company={company} />
          {!company?.logo_data_url && <span>{company?.company_name ?? "HRMS"}</span>}
        </div>
        <div>
          <h2>{company ? `Welcome to ${company.company_name}` : kicker}</h2>
          <p>One workspace for people, branches, leave, and payroll — with country rules that stay configurable.</p>
        </div>
        {company ? <div className="auth-points"><div><strong>Your company portal</strong><span>Manage your work, reviews, leave and attendance in one place.</span></div><div><strong>Secure access</strong><span>Sign in with your HR-issued account.</span></div></div> : <div className="auth-points">
          <div>
            <strong>Multi-company</strong>
            <span>Switch company and branch without mixing records.</span>
          </div>
          <div>
            <strong>East Africa ready</strong>
            <span>Kenya, Uganda, Tanzania, Rwanda — and more as you expand.</span>
          </div>
          <div>
            <strong>14-day trial</strong>
            <span>Your first company and head office are created at signup.</span>
          </div>
        </div>
        }
      </aside>
      <main className="auth-main">
        <div className="auth-wrap">
          <div className="auth-top">
            <CompanyLogo company={company} />
            {!company?.logo_data_url && <span>{company?.company_name ?? "HRMS"}</span>}
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
