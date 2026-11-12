import CompanyDomains from "../../components/CompanyDomains";
import BrandingSettings from "../../components/BrandingSettings";
import RolesSettings from "../../components/RolesSettings";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api";
import { DocumentCategories } from "../../components/DocumentCategories";
import type { Company, DocumentCategory } from "../../types";
import { AuditLogs } from "../../components/AuditLogs";
import { Card, FormSkeleton, PageHeader, StatusPill } from "../../ui";

const sections = ["Company", "Branding", "Domains", "Documents", "Roles", "Localisation", "Notifications", "Audit log"];

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export default function SettingsPage() {
  const { token, user, tenant, company, branch, canManageOrg, hasPermission, reloadOrg, notify } = useWorkspace();
  const [section, setSection] = useState("Company");
  const [name, setName] = useState(company?.name ?? "");
  const [legalName, setLegalName] = useState(company?.legal_name ?? "");
  const [email, setEmail] = useState(company?.email ?? "");
  const [phone, setPhone] = useState(company?.phone ?? "");
  const [status, setStatus] = useState(company?.status ?? "ACTIVE");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<DocumentCategory[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(false);

  useEffect(() => {
    setName(company?.name ?? "");
    setLegalName(company?.legal_name ?? "");
    setEmail(company?.email ?? "");
    setPhone(company?.phone ?? "");
    setStatus(company?.status ?? "ACTIVE");
  }, [company]);

  useEffect(() => {
    if (!company || !token) {
      setCategories([]);
      return;
    }
    setCategoriesLoading(true);
    api<DocumentCategory[]>(`/document-categories?company_id=${company.id}`, { token })
      .then(setCategories)
      .catch(() => setCategories([]))
      .finally(() => setCategoriesLoading(false));
  }, [company?.id, token]);

  async function saveCompany(event: FormEvent) {
    event.preventDefault();
    if (!company || !canManageOrg) return;
    setBusy(true);
    setError(null);
    try {
      await api<Company>(`/companies/${company.id}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({
          name: name.trim(),
          legal_name: blankToNull(legalName),
          email: blankToNull(email),
          phone: blankToNull(phone),
          status,
        }),
      });
      await reloadOrg({ companyId: company.id });
      notify("Company saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Workspace"
        description="Plan, access, and the company you are working in. Add legal entities and sites from Companies and Branches."
        actions={
          <>
            <Link className="btn ghost small" to="/app/companies">Companies</Link>
            <Link className="btn ghost small" to="/app/branches">Branches</Link>
            <Link className="btn ghost small" to="/app/documents">Documents</Link>
          </>
        }
      />
      <div className="page-tabs">
        {sections.filter(item => item !== "Domains" || hasPermission("domains.manage")).filter((item) => item !== "Roles" || hasPermission("access.manage_roles")).filter((item) => item !== "Audit log" || hasPermission("audit.view")).map((item) => (
          <button key={item} type="button" className={section === item ? "active" : ""} onClick={() => setSection(item)}>
            {item}
          </button>
        ))}
      </div>

      {section === "Domains" && company && hasPermission("domains.manage") ? <CompanyDomains key={company.id} companyId={company.id} token={token} /> : null}
      {section === "Company" ? (
        !company ? (
        <section className="card card-pad" aria-busy="true">
          <FormSkeleton compact fields={7} />
        </section>
        ) : (
        <form className="card card-pad" onSubmit={saveCompany}>
          <div className="form-grid">
            <label>Workspace<input readOnly value={tenant?.name ?? ""} /></label>
            <label>Plan<input readOnly value={tenant?.subscription_tier ?? ""} /></label>
            <label>Company name<input required value={name} onChange={(event) => setName(event.target.value)} readOnly={!canManageOrg} /></label>
            <label>Legal name<input value={legalName} onChange={(event) => setLegalName(event.target.value)} readOnly={!canManageOrg} /></label>
            <label>Status
              <select value={status} onChange={(event) => setStatus(event.target.value)} disabled={!canManageOrg}>
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
              </select>
            </label>
            <label>Contact email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} readOnly={!canManageOrg} /></label>
            <label>Phone<input value={phone} onChange={(event) => setPhone(event.target.value)} readOnly={!canManageOrg} /></label>
          </div>
          {error ? <p className="error">{error}</p> : null}
          {canManageOrg ? <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button> : null}
        </form>
        )
      ) : null}

      {section === "Branding" && company ? <Card title="Company branding" padded><BrandingSettings key={company.id} company={company} token={token} canManage={canManageOrg} onSaved={async () => { await reloadOrg({ companyId: company.id }); notify("Company branding saved."); }} /></Card> : null}

      {section === "Documents" ? (
        <Card title="Document categories">
          {!company || categoriesLoading ? (
            <FormSkeleton compact fields={4} />
          ) : (
            <DocumentCategories
              token={token}
              apiBase=""
              companyId={company.id}
              rows={categories}
              canManage={hasPermission("documents.manage")}
              onChange={setCategories}
            />
          )}
        </Card>
      ) : null}

      {section === "Roles" ? <RolesSettings /> : null}

      {section === "Localisation" ? (
        <Card padded title="Country & localisation">
          <p className="muted">
            Branch country selects timezone, currency, and the payroll pack. There is no Kenya-only logic in this screen —
            packs are loaded from the platform country catalogue.
          </p>
        </Card>
      ) : null}

      {section === "Notifications" ? (
        <Card padded title="Notifications">
          <label style={{ fontWeight: 500 }}>
            <input type="checkbox" defaultChecked /> Email me when leave needs approval
          </label>
          <label style={{ fontWeight: 500, marginTop: 8 }}>
            <input type="checkbox" defaultChecked /> Email me when a payroll run is ready
          </label>
        </Card>
      ) : null}

      {section === "Audit log" ? (
        <Card title="Audit log">
          {token ? (
            <AuditLogs token={token} path="/auth/audit-logs" timeZone={branch?.timezone} />
          ) : (
            <p className="muted">Sign in to view requests for this workspace.</p>
          )}
        </Card>
      ) : null}

      <p className="muted" style={{ marginTop: 12 }}>Signed in as {user.email} · {user.role} · <StatusPill value={user.status} /></p>
    </>
  );
}
