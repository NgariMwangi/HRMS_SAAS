import { PageHeader, Skel } from "../../ui";

const items = [
  { name: "School management", detail: "Share staff records with a campus system when an integration is authorised." },
  { name: "Accounting export", detail: "Send approved payroll journals. Mapping is per country and currency." },
  { name: "Identity provider", detail: "SSO for employees. Not configured in this workspace yet." },
];

export default function IntegrationsPage() {
  const loading = false;
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect HRMS to the rest of the business without copying spreadsheets."
      />
      {loading ? (
        <div className="stack" aria-busy="true">
          {Array.from({ length: 3 }, (_, index) => (
            <section className="card card-pad" key={index}>
              <Skel w={180} h={16} />
              <div style={{ marginTop: 10 }}><Skel w="80%" h={12} /></div>
            </section>
          ))}
        </div>
      ) : (
      <div className="stack">
        {items.map((item) => (
          <section className="card card-pad" key={item.name}>
            <div className="page-head" style={{ marginBottom: 0 }}>
              <div>
                <h3 style={{ fontSize: "1rem" }}>{item.name}</h3>
                <p>{item.detail}</p>
              </div>
              <button className="btn ghost small" type="button">Configure</button>
            </div>
          </section>
        ))}
      </div>
      )}
    </>
  );
}
