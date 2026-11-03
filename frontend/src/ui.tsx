import { ReactNode } from "react";

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function StatusPill({ value }: { value: string }) {
  const tone = value.toLowerCase().replace(/\s+/g, "-");
  return <span className={`pill pill-${tone}`}>{value.toLowerCase()}</span>;
}

function parseInstant(value: string): Date {
  const text = value.trim();
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(text)) return new Date(text);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return new Date(`${text}T00:00:00Z`);
  return new Date(`${text}Z`);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = parseInstant(value);
  if (Number.isNaN(date.getTime())) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
    const [year, month, day] = value.trim().split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined, timeZone?: string | null): string {
  if (!value) return "—";
  const date = parseInstant(value);
  if (Number.isNaN(date.getTime())) return "—";
  const options: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  };
  if (timeZone) options.timeZone = timeZone;
  try {
    return date.toLocaleString(undefined, options);
  } catch {
    delete options.timeZone;
    return date.toLocaleString(undefined, options);
  }
}

export function formatMoney(value: string | number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: currency ? "currency" : "decimal",
      currency: currency || "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return amount.toLocaleString();
  }
}

export function matchesSearch(query: string, ...parts: Array<string | null | undefined>): boolean {
  const term = query.trim().toLowerCase();
  if (!term) return true;
  return parts.some((part) => (part ?? "").toLowerCase().includes(term));
}

export function SearchField({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label>
      Search
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="search-field"
        placeholder={placeholder}
      />
    </label>
  );
}

export function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      className="btn ghost icon small"
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function EmptyState({ title, note, action }: { title: string; note: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {note}
      {action ? <div style={{ marginTop: 12 }}>{action}</div> : null}
    </div>
  );
}

export function Avatar({ name, size = "md", src }: { name: string; size?: "sm" | "md" | "lg"; src?: string | null }) {
  if (src) return <img className={`avatar ${size}`} src={src} alt={name} />;
  const letters = initials(name);
  return <span className={`avatar ${size}${letters.length === 1 ? " single" : ""}`}>{letters}</span>;
}

export function PageHeader({
  title,
  description,
  actions,
  preview,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  preview?: boolean;
}) {
  return (
    <div className="page-head">
      <div>
        <div className="title-row">
          <h1>{title}</h1>
          {preview ? <span className="preview">Preview data</span> : null}
        </div>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
  );
}

export function Kpi({
  label,
  value,
  hint,
  down,
  icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  down?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div className="kpi">
      <div className="kpi-top">
        <span>{label}</span>
        {icon ? <span className="kpi-ico">{icon}</span> : null}
      </div>
      <strong>{value}</strong>
      {hint ? <em className={down ? "down" : ""}>{hint}</em> : null}
    </div>
  );
}

export function Skel({
  w = "100%",
  h = 12,
  variant,
}: {
  w?: number | string;
  h?: number | string;
  variant?: "avatar" | "photo" | "pill";
}) {
  return (
    <span
      className={`skel${variant ? ` skel-${variant}` : ""}`}
      style={{ width: typeof w === "number" ? `${w}px` : w, height: typeof h === "number" ? `${h}px` : h }}
      aria-hidden="true"
    />
  );
}

export function TableSkeleton({ rows = 6, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <table aria-hidden="true">
      <thead>
        <tr>
          {Array.from({ length: cols }, (_, index) => (
            <th key={index}><Skel w={index === 0 ? 110 : 72} /></th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: rows }, (_, row) => (
          <tr key={row}>
            {Array.from({ length: cols }, (_, col) => (
              <td key={col}>
                {col === 0 ? (
                  <div className="person">
                    <Skel variant="avatar" w={36} h={36} />
                    <div style={{ flex: 1, display: "grid", gap: 6 }}>
                      <Skel w="58%" />
                      <Skel w="40%" h={10} />
                    </div>
                  </div>
                ) : (
                  <Skel w={col === cols - 1 ? 52 : 86} />
                )}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ProfileSkeleton() {
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="page-head">
        <div>
          <Skel w={88} h={10} />
          <div style={{ marginTop: 12 }}><Skel w={240} h={24} /></div>
          <div style={{ marginTop: 10 }}><Skel w={280} h={12} /></div>
        </div>
      </div>
      <section className="card card-pad">
        <div className="profile-id">
          <Skel variant="photo" w={148} h={185} />
          <dl className="meta-grid">
            {Array.from({ length: 10 }, (_, index) => (
              <div key={index}>
                <Skel w={72} h={10} />
                <div style={{ marginTop: 8 }}><Skel w="72%" h={14} /></div>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}

export function FormSkeleton({ compact = false, fields = 6 }: { compact?: boolean; fields?: number }) {
  const fieldsGrid = (
    <div className="form-grid">
      {Array.from({ length: fields }, (_, index) => (
        <div key={index}>
          <Skel w={90} h={10} />
          <div style={{ marginTop: 8 }}><Skel w="100%" h={40} /></div>
        </div>
      ))}
    </div>
  );
  if (compact) {
    return (
      <div aria-busy="true" aria-live="polite">
        {fieldsGrid}
      </div>
    );
  }
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="page-head">
        <div>
          <Skel w={88} h={10} />
          <div style={{ marginTop: 12 }}><Skel w={180} h={24} /></div>
        </div>
      </div>
      <section className="card card-pad">{fieldsGrid}</section>
    </div>
  );
}

export function KpiRowSkeleton({ count = 4, className = "kpis" }: { count?: number; className?: string }) {
  return (
    <div className={className} aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div className="kpi" key={index}>
          <Skel w="42%" h={10} />
          <div style={{ marginTop: 14 }}><Skel w="58%" h={26} /></div>
          <div style={{ marginTop: 10 }}><Skel w="68%" h={10} /></div>
        </div>
      ))}
    </div>
  );
}

export function PageSkeleton({
  kpis = false,
  rows = 6,
  cols = 5,
}: {
  kpis?: boolean;
  rows?: number;
  cols?: number;
}) {
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="page-head">
        <div>
          <Skel w={170} h={24} />
          <div style={{ marginTop: 10 }}><Skel w={300} h={12} /></div>
        </div>
        <div className="actions">
          <Skel variant="pill" w={92} h={32} />
        </div>
      </div>
      {kpis ? <KpiRowSkeleton /> : null}
      <section className="card">
        <TableSkeleton rows={rows} cols={cols} />
      </section>
    </div>
  );
}

export function ModulePlaceholder({
  title,
  description,
  actions,
  loading = false,
  kpis,
  emptyTitle,
  emptyNote,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  loading?: boolean;
  kpis?: boolean;
  emptyTitle: string;
  emptyNote: string;
}) {
  if (loading) return <PageSkeleton kpis={kpis} />;
  return (
    <>
      <PageHeader title={title} description={description} actions={actions} />
      <section className="card">
        <EmptyState title={emptyTitle} note={emptyNote} />
      </section>
    </>
  );
}

export function SplitPageSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="page-head">
        <div>
          <Skel w={170} h={24} />
          <div style={{ marginTop: 10 }}><Skel w={280} h={12} /></div>
        </div>
      </div>
      <div className="filters" style={{ marginBottom: 14 }}>
        <Skel w={200} h={40} />
      </div>
      <div className="grid-2">
        <section className="card">
          <TableSkeleton rows={6} cols={cols} />
        </section>
        <section className="card card-pad">
          <FormSkeleton compact fields={4} />
        </section>
      </div>
    </div>
  );
}

export function Card({
  title,
  note,
  action,
  children,
  padded = false,
}: {
  title?: string;
  note?: string;
  action?: ReactNode;
  children: ReactNode;
  padded?: boolean;
}) {
  return (
    <section className="card">
      {title ? (
        <div className="card-head">
          <div>
            <h3>{title}</h3>
            {note ? <p>{note}</p> : null}
          </div>
          {action}
        </div>
      ) : null}
      {padded ? <div className="card-pad">{children}</div> : children}
    </section>
  );
}

export function PersonCell({ name, email, photo }: { name: string; email?: string; photo?: string | null }) {
  return (
    <div className="person">
      <Avatar name={name} src={photo} />
      <div>
        <strong>{name}</strong>
        {email ? <span>{email}</span> : null}
      </div>
    </div>
  );
}

export function LineChart({ points }: { points: { label: string; value: number }[] }) {
  const width = 520;
  const height = 180;
  const max = Math.max(...points.map((p) => p.value), 1);
  const min = Math.min(...points.map((p) => p.value), 0);
  const span = Math.max(max - min, 1);
  const coords = points.map((point, index) => {
    const x = (index / Math.max(points.length - 1, 1)) * (width - 24) + 8;
    const y = height - 24 - ((point.value - min) / span) * (height - 40);
    return `${x},${y}`;
  });
  return (
    <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Headcount trend">
      <polyline fill="none" stroke="currentColor" strokeWidth="2.5" points={coords.join(" ")} />
      {points.map((point, index) => {
        const [x, y] = coords[index].split(",");
        return (
          <g key={point.label}>
            <circle cx={x} cy={y} r="3.5" fill="currentColor" />
            <text x={x} y={height - 6} textAnchor="middle" fontSize="11">
              {point.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function BarChart({ items }: { items: { label: string; value: number }[] }) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="bar-chart">
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span>{item.label}</span>
          <div className="bar-track">
            <i style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}
