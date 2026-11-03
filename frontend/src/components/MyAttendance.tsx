import { useEffect, useState } from "react";
import { api } from "../api";
import { useWorkspace } from "../context/WorkspaceContext";
import type { AttendanceRow } from "../types";
import { Card, formatDateTime, PageHeader, StatusPill } from "../ui";

export default function MyAttendance() {
  const { user, notify } = useWorkspace();
  const [row, setRow] = useState<AttendanceRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!user.employee_id) return;
    api<AttendanceRow>("/attendance/me").then(setRow).catch((err: Error) => setError(err.message));
  }, [user.employee_id]);

  async function clock(action: "clock-in" | "clock-out") {
    setBusy(true); setError(null);
    try {
      let device = localStorage.getItem("hrms_clock_device_id");
      if (!device) { device = crypto.randomUUID(); localStorage.setItem("hrms_clock_device_id", device); }
      const saved = await api<AttendanceRow>(`/attendance/${action}`, { method: "POST", body: JSON.stringify({ device_id: device }) });
      setRow(saved); notify(action === "clock-in" ? "Clocked in." : "Clocked out.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update attendance"); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader title="My attendance" description="Clock in and out for your own employee record." />
    <Card padded title={row?.work_on ?? "Today"}>
      {!user.employee_id ? <p className="muted">Ask HR to link your login to an employee record.</p> : <>
        {row ? <><StatusPill value={row.status} /><p>In: {formatDateTime(row.checked_in_at)} · Out: {formatDateTime(row.checked_out_at)}</p></> : null}
        <div className="actions">
          <button className="btn" type="button" disabled={busy || !row || !!row.checked_in_at || row.on_leave} onClick={() => void clock("clock-in")}>Clock in</button>
          <button className="btn ghost" type="button" disabled={busy || !row?.checked_in_at || !!row.checked_out_at || row.on_leave} onClick={() => void clock("clock-out")}>Clock out</button>
        </div>
      </>}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </Card>
  </>;
}
