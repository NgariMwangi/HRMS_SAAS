import { FormEvent, useEffect, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api, apiUrl } from "../../api";
import { BenefitTypes } from "../../components/BenefitTypes";
import { DeductionTypes } from "../../components/DeductionTypes";
import type { PayrollSettings } from "../../types";
import { FormSkeleton, PageHeader, formatDate } from "../../ui";

export type PayrollSettingsScope = {
  token: string;
  apiBase?: string;
  company: { id: string; name: string } | null;
  branch: { id: string; name: string } | null;
  canManageHr: boolean;
  notify: (message: string) => void;
  hideHeader?: boolean;
};

export function PayrollSettingsForm({
  token,
  apiBase = "",
  company,
  branch,
  canManageHr,
  notify,
  hideHeader,
}: PayrollSettingsScope) {
  const [settings, setSettings] = useState<PayrollSettings | null>(null);
  const [frequency, setFrequency] = useState("MONTHLY");
  const [structure, setStructure] = useState("GROSS_ONLY");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!company) {
      setSettings(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const query = apiUrl(
        apiBase,
        `/payroll/settings?company_id=${company.id}${branch ? `&branch_id=${branch.id}` : ""}`,
      );
      const row = await api<PayrollSettings>(query, { token });
      setSettings(row);
      setFrequency(row.frequency);
      setStructure(row.salary_structure);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load configuration");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [company?.id, branch?.id, token, apiBase]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!company || !canManageHr) return;
    setBusy(true);
    try {
      const query = apiUrl(
        apiBase,
        `/payroll/settings?company_id=${company.id}${branch ? `&branch_id=${branch.id}` : ""}`,
      );
      const row = await api<PayrollSettings>(query, {
        method: "PUT",
        token,
        body: JSON.stringify({ frequency, salary_structure: structure }),
      });
      setSettings(row);
      notify("Payroll configuration saved.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {hideHeader ? null : (
        <PageHeader
          title="Payroll configuration"
          description="Country, currency, and statutory pack come from the active branch. This screen only stores the pay calendar and default salary structure."
        />
      )}
      {loading ? (
        <section className="card card-pad" aria-busy="true">
          <FormSkeleton compact fields={4} />
        </section>
      ) : (
        <form className="card card-pad" onSubmit={save}>
          <div className="form-grid">
            <label>Company<input readOnly value={company?.name ?? ""} /></label>
            <label>Branch<input readOnly value={branch?.name ?? ""} /></label>
            <label>Country<input readOnly value={settings?.country_name ? `${settings.country_name} (${settings.country_code})` : "Select a branch"} /></label>
            <label>Currency<input readOnly value={settings?.currency_code ?? "Inherited from branch country"} /></label>
            <label>
              Payroll frequency
              <select value={frequency} onChange={(event) => setFrequency(event.target.value)} disabled={!canManageHr}>
                <option value="MONTHLY">Monthly</option>
                <option value="BIWEEKLY">Bi-weekly</option>
                <option value="WEEKLY">Weekly</option>
              </select>
            </label>
            <label>
              Default salary structure
              <select value={structure} onChange={(event) => setStructure(event.target.value)} disabled={!canManageHr}>
                <option value="GROSS_ONLY">Gross only</option>
                <option value="BASIC_PLUS_ALLOWANCES">Basic + allowances</option>
              </select>
            </label>
          </div>
          <p className="muted">
            {settings?.pack_status === "PUBLISHED"
              ? `Using ${settings.country_code} pack v${settings.pack_version}, effective ${formatDate(settings.pack_effective_from)}.`
              : "This branch country has no published payroll pack yet. Platform admin must publish one before a run."}
          </p>
          {error ? <p className="error">{error}</p> : null}
          {canManageHr ? (
            <div className="actions">
              <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            </div>
          ) : null}
        </form>
      )}
      <BenefitTypes
        token={token}
        apiBase={apiBase}
        company={company}
        currency={settings?.currency_code}
        canManage={canManageHr}
        notify={notify}
      />

      <DeductionTypes
        token={token}
        apiBase={apiBase}
        company={company}
        branch={branch}
        currency={settings?.currency_code}
        canManage={canManageHr}
        notify={notify}
      />
    </>
  );
}

export default function PayrollSettingsPage() {
  const { token, company, branch, notify, hasPermission } = useWorkspace();
  return (
    <PayrollSettingsForm
      token={token}
      company={company}
      branch={branch}
      canManageHr={hasPermission("payroll.manage")}
      notify={notify}
    />
  );
}
