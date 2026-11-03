import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminToken, api } from "./api";
import type { Overview } from "./types";

export default function AdminOverview() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Overview>("/platform/overview", { token: adminToken.get() })
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>Loading…</p>;

  const cards = [
    ["Tenants", data.tenant_count],
    ["Active", data.active_tenant_count],
    ["Trials", data.trial_count],
    ["Companies", data.company_count],
    ["Users", data.user_count],
    ["Branches", data.branch_count],
  ] as const;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>Platform</h1>
        </div>
        <Link className="button-link" to="/admin/tenants">
          View tenants
        </Link>
      </header>
      <section className="stats">
        {cards.map(([label, value]) => (
          <article key={label} className="stat">
            <p>{label}</p>
            <strong>{value}</strong>
          </article>
        ))}
      </section>
    </>
  );
}
