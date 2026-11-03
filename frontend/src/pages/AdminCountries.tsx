import { useEffect, useMemo, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { adminToken, api } from "../api";
import type { Country } from "../types";
import { EmptyState, matchesSearch, PageHeader, SearchField, StatusPill, TableSkeleton } from "../ui";

export default function AdminCountries() {
  const navigate = useNavigate();
  const token = adminToken.get();
  const [countries, setCountries] = useState<Country[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      navigate("/admin/login");
      return;
    }
    api<Country[]>("/platform/countries", { token })
      .then(setCountries)
      .catch(() => {
        adminToken.clear();
        navigate("/admin/login");
      })
      .finally(() => setLoading(false));
  }, [navigate, token]);

  async function toggle(country: Country) {
    if (!token) return;
    setBusy(true);
    try {
      const updated = await api<Country>(`/platform/countries/${country.id}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({ is_active: !country.is_active }),
      });
      setCountries((rows) => rows.map((row) => (row.id === country.id ? { ...row, ...updated } : row)));
    } finally {
      setBusy(false);
    }
  }

  const visible = useMemo(
    () => countries.filter((row) => matchesSearch(query, row.name, row.code, row.default_currency?.code, row.default_timezone)),
    [countries, query],
  );

  return (
    <>
      <PageHeader
        title="Countries"
        description="Platform-owned catalogue. Tenants can read these, not edit them."
      />
      <div className="filters">
        <SearchField value={query} onChange={setQuery} placeholder="Name, code, or currency" />
      </div>
      <section className="card">
        {loading ? (
          <TableSkeleton rows={8} cols={6} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={query.trim() ? "No matching countries" : "No countries"}
            note={query.trim() ? `Nothing matched “${query.trim()}”.` : "The platform catalogue is empty."}
          />
        ) : (
        <>
        <table>
          <thead>
            <tr>
              <th>Country</th>
              <th>Code</th>
              <th>Currency</th>
              <th>Timezone</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((country) => (
              <tr key={country.id}>
                <td data-label="Country">{country.name}</td>
                <td data-label="Code">{country.code}</td>
                <td data-label="Currency">{country.default_currency?.code ?? "—"}</td>
                <td data-label="Timezone">{country.default_timezone ?? "—"}</td>
                <td data-label="Status"><StatusPill value={country.is_active ? "ACTIVE" : "INACTIVE"} /></td>
                <td>
                  <Link className="btn ghost small" to={`/admin/countries/${country.id}/packs`}>Payroll pack</Link>
                  <button className="btn ghost small" type="button" disabled={busy} onClick={() => toggle(country)}>
                    {country.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="paginate">
          <span>{visible.length} of {countries.length} countries</span>
          <span>Page 1 of 1</span>
        </div>
        </>
        )}
      </section>
    </>
  );
}
