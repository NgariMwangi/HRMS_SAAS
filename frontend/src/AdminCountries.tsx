import { useEffect, useState } from "react";
import { adminToken, api } from "./api";
import type { Country } from "./types";
import { StatusPill } from "./ui";

export default function AdminCountries() {
  const [countries, setCountries] = useState<Country[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const rows = await api<Country[]>("/platform/countries", {
      token: adminToken.get(),
    });
    setCountries(rows);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  async function toggle(country: Country) {
    setError(null);
    try {
      await api(`/platform/countries/${country.id}`, {
        method: "PATCH",
        token: adminToken.get(),
        body: JSON.stringify({ is_active: !country.is_active }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Reference data</p>
          <h1>Countries</h1>
        </div>
      </header>
      {error ? <p className="error">{error}</p> : null}
      <article className="card">
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
            {countries.map((country) => (
              <tr key={country.id}>
                <td>{country.name}</td>
                <td>{country.code}</td>
                <td>{country.default_currency?.code ?? "—"}</td>
                <td>{country.default_timezone ?? "—"}</td>
                <td>
                  <StatusPill value={country.is_active ? "ACTIVE" : "INACTIVE"} />
                </td>
                <td>
                  <button
                    type="button"
                    className="tiny"
                    onClick={() => toggle(country)}
                  >
                    {country.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </>
  );
}
