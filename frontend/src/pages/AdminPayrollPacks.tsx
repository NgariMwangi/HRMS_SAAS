import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { adminToken, api } from "../api";
import type { PayrollPack, PayrollPackSummary } from "../types";
import { EmptyState, PageHeader, StatusPill, TableSkeleton, formatDate } from "../ui";

export default function AdminPayrollPacks() {
  const { countryId } = useParams();
  const navigate = useNavigate();
  const token = adminToken.get();
  const [rows, setRows] = useState<PayrollPackSummary[]>([]);
  const [selected, setSelected] = useState<PayrollPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!token || !countryId) return;
    const list = await api<PayrollPackSummary[]>(`/platform/payroll-packs?country_id=${countryId}`, { token });
    setRows(list);
    if (list[0]) {
      const detail = await api<PayrollPack>(`/platform/payroll-packs/${list[0].id}`, { token });
      setSelected(detail);
    } else {
      setSelected(null);
    }
  }

  useEffect(() => {
    if (!token) {
      navigate("/admin/login");
      return;
    }
    load()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [countryId, navigate, token]);

  const countryCode = rows[0]?.country_code ?? selected?.country_code;

  async function openPack(id: string) {
    if (!token) return;
    setBusy(true);
    try {
      setSelected(await api<PayrollPack>(`/platform/payroll-packs/${id}`, { token }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load pack");
    } finally {
      setBusy(false);
    }
  }

  async function newVersion() {
    if (!token || !countryId || !selected) return;
    setBusy(true);
    try {
      const created = await api<PayrollPack>("/platform/payroll-packs", {
        method: "POST",
        token,
        body: JSON.stringify({
          country_id: countryId,
          effective_from: new Date().toISOString().slice(0, 10),
          copy_from_id: selected.id,
        }),
      });
      await load();
      setSelected(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create version");
    } finally {
      setBusy(false);
    }
  }

  function persistDraft(pack: PayrollPack, authToken: string) {
    return api<PayrollPack>(`/platform/payroll-packs/${pack.id}`, {
        method: "PUT",
        token: authToken,
        body: JSON.stringify({
          effective_from: pack.effective_from,
          constants: pack.constants.map((row) => ({ key: row.key, amount: row.amount })),
          components: pack.components.map((item) => ({
            code: item.code,
            name: item.name,
            party: item.party,
            formula_kind: item.formula_kind,
            base: item.base,
            percent: item.percent,
            cap: item.cap,
            floor: item.floor,
            amount: item.amount,
            min_amount: item.min_amount,
            relief_key: item.relief_key,
            reduces_taxable: item.reduces_taxable,
            sort_order: item.sort_order,
            bands: item.bands.map((band) => ({
              from_amount: band.from_amount,
              to_amount: band.to_amount,
              rate_percent: band.rate_percent,
              sort_order: band.sort_order,
            })),
          })),
        }),
      });
  }

  async function saveDraft() {
    if (!token || !selected || selected.status !== "DRAFT") return;
    setBusy(true);
    try {
      const saved = await persistDraft(selected, token);
      setSelected(saved);
      setRows((current) => current.map((row) => (row.id === saved.id ? { ...row, effective_from: saved.effective_from } : row)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!token || !selected) return;
    setBusy(true);
    try {
      if (selected.status === "DRAFT") await persistDraft(selected, token);
      const saved = await api<PayrollPack>(`/platform/payroll-packs/${selected.id}/publish`, { method: "POST", token });
      setSelected(saved);
      setRows((current) =>
        current.map((row) => (row.id === saved.id ? { ...row, status: saved.status, effective_from: saved.effective_from } : row)),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not publish");
    } finally {
      setBusy(false);
    }
  }

  const draft = selected?.status === "DRAFT";
  const openDraft = rows.find((row) => row.status === "DRAFT");

  const constants = useMemo(() => selected?.constants ?? [], [selected]);

  return (
    <>
      <PageHeader
        title={`Payroll packs${countryCode ? ` · ${countryCode}` : ""}`}
        description="Statutory tables for this country. Numbers are data — create a new version when a gazette changes."
        actions={<Link className="btn ghost small" to="/admin/countries">Countries</Link>}
      />
      {error ? <p className="error">{error}</p> : null}
      {loading ? (
        <section className="card"><TableSkeleton cols={4} /></section>
      ) : rows.length === 0 ? (
        <section className="card">
          <EmptyState title="No pack yet" note="Seed creates Kenya, Uganda, and Tanzania packs. Rwanda stays without a pack until you add one." />
        </section>
      ) : (
        <>
          <section className="card">
            <table>
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Effective</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td data-label="Version">v{row.version}</td>
                    <td data-label="Effective">{formatDate(row.effective_from)}</td>
                    <td data-label="Status"><StatusPill value={row.status} /></td>
                    <td>
                      <button className="btn ghost small" type="button" disabled={busy} onClick={() => void openPack(row.id)}>Open</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {selected ? (
            <section className="card card-pad">
              {draft ? (
                <div style={{ marginBottom: "1rem" }}>
                  <h3 style={{ margin: "0 0 0.35rem" }}>Editing draft v{selected.version}</h3>
                  <p className="muted" style={{ marginTop: 0 }}>
                    Payroll ignores this version until you publish it. Once published it is locked.
                  </p>
                  <div className="form-grid">
                    <label>
                      Effective from
                      <input
                        type="date"
                        value={selected.effective_from}
                        onChange={(event) => setSelected({ ...selected, effective_from: event.target.value })}
                      />
                    </label>
                  </div>
                  <div className="actions">
                    <button className="btn small" type="button" disabled={busy} onClick={() => void saveDraft()}>Save draft</button>
                    <button className="btn small" type="button" disabled={busy} onClick={() => void publish()}>Publish</button>
                  </div>
                </div>
              ) : (
                <div style={{ marginBottom: "1rem" }}>
                  <h3 style={{ margin: "0 0 0.35rem" }}>v{selected.version} is published and locked</h3>
                  <p className="muted" style={{ marginTop: 0 }}>
                    Published rates stay fixed so past payroll runs can be reproduced. To change a rate, edit a draft copy and publish it.
                  </p>
                  <div className="actions">
                    {openDraft ? (
                      <button className="btn small" type="button" disabled={busy} onClick={() => void openPack(openDraft.id)}>
                        Continue editing draft v{openDraft.version}
                      </button>
                    ) : (
                      <button className="btn small" type="button" disabled={busy} onClick={() => void newVersion()}>
                        Create draft to edit
                      </button>
                    )}
                  </div>
                </div>
              )}
              {constants.length ? (
                <div className="form-grid">
                  {constants.map((row, index) => (
                    <label key={row.id}>
                      {row.key}
                      <input
                        value={row.amount}
                        disabled={!draft}
                        onChange={(event) => {
                          const next = selected.constants.map((item, i) => (i === index ? { ...item, amount: event.target.value } : item));
                          setSelected({ ...selected, constants: next });
                        }}
                      />
                    </label>
                  ))}
                </div>
              ) : null}
              {selected.components.map((item, componentIndex) => (
                <div key={item.id} style={{ marginTop: "1.25rem" }}>
                  <h3 style={{ marginBottom: "0.35rem" }}>{item.name} <StatusPill value={item.party} /></h3>
                  <p className="muted">{item.formula_kind.replaceAll("_", " ").toLowerCase()} of {item.base.toLowerCase()}</p>
                  {item.formula_kind === "PERCENT" ? (
                    <div className="form-grid">
                      <label>
                        Percent
                        <input
                          value={item.percent ?? ""}
                          disabled={!draft}
                          onChange={(event) => {
                            const components = selected.components.map((row, i) => (i === componentIndex ? { ...row, percent: event.target.value } : row));
                            setSelected({ ...selected, components });
                          }}
                        />
                      </label>
                      <label>
                        Earnings from
                        <input
                          value={item.floor ?? ""}
                          disabled={!draft}
                          onChange={(event) => {
                            const components = selected.components.map((row, i) => (i === componentIndex ? { ...row, floor: event.target.value || null } : row));
                            setSelected({ ...selected, components });
                          }}
                        />
                      </label>
                      <label>
                        Earnings to
                        <input
                          value={item.cap ?? ""}
                          disabled={!draft}
                          onChange={(event) => {
                            const components = selected.components.map((row, i) => (i === componentIndex ? { ...row, cap: event.target.value || null } : row));
                            setSelected({ ...selected, components });
                          }}
                        />
                      </label>
                      <label>
                        Min contribution
                        <input
                          value={item.min_amount ?? ""}
                          disabled={!draft}
                          onChange={(event) => {
                            const components = selected.components.map((row, i) => (i === componentIndex ? { ...row, min_amount: event.target.value || null } : row));
                            setSelected({ ...selected, components });
                          }}
                        />
                      </label>
                      <label>
                        Max contribution
                        <input
                          value={item.amount ?? ""}
                          disabled={!draft}
                          onChange={(event) => {
                            const components = selected.components.map((row, i) => (i === componentIndex ? { ...row, amount: event.target.value || null } : row));
                            setSelected({ ...selected, components });
                          }}
                        />
                      </label>
                    </div>
                  ) : null}
                  {item.bands.length ? (
                    <table className="org-table">
                      <thead>
                        <tr>
                          <th>From</th>
                          <th>To</th>
                          <th>Rate %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {item.bands.map((band, bandIndex) => (
                          <tr key={band.id}>
                            <td>
                              <input
                                value={band.from_amount}
                                disabled={!draft}
                                onChange={(event) => {
                                  const components = selected.components.map((row, i) => {
                                    if (i !== componentIndex) return row;
                                    const bands = row.bands.map((b, j) => (j === bandIndex ? { ...b, from_amount: event.target.value } : b));
                                    return { ...row, bands };
                                  });
                                  setSelected({ ...selected, components });
                                }}
                              />
                            </td>
                            <td>
                              <input
                                value={band.to_amount ?? ""}
                                disabled={!draft}
                                onChange={(event) => {
                                  const components = selected.components.map((row, i) => {
                                    if (i !== componentIndex) return row;
                                    const bands = row.bands.map((b, j) => (j === bandIndex ? { ...b, to_amount: event.target.value || null } : b));
                                    return { ...row, bands };
                                  });
                                  setSelected({ ...selected, components });
                                }}
                              />
                            </td>
                            <td>
                              <input
                                value={band.rate_percent}
                                disabled={!draft}
                                onChange={(event) => {
                                  const components = selected.components.map((row, i) => {
                                    if (i !== componentIndex) return row;
                                    const bands = row.bands.map((b, j) => (j === bandIndex ? { ...b, rate_percent: event.target.value } : b));
                                    return { ...row, bands };
                                  });
                                  setSelected({ ...selected, components });
                                }}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : null}
                </div>
              ))}
              <p className="muted">Percent of the earnings slice (from → to), raised to the min contribution when lower and capped at the max contribution. Kenya NSSF is two 6% tiers with a matching employer line each.</p>
            </section>
          ) : null}
        </>
      )}
    </>
  );
}
