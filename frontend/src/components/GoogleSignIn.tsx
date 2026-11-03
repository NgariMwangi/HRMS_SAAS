import { useEffect, useRef, useState } from "react";
import { api } from "../api";

type GoogleApi = { accounts: { id: {
  initialize: (options: { client_id: string; nonce: string; callback: (response: { credential: string }) => void; auto_select: boolean }) => void;
  renderButton: (element: HTMLElement, options: Record<string, string | number>) => void;
} } };
declare global { interface Window { google?: GoogleApi } }
let scriptPromise: Promise<void> | null = null;
function loadGoogle() {
  if (window.google) return Promise.resolve();
  if (!scriptPromise) scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script"); script.src = "https://accounts.google.com/gsi/client";
    script.async = true; script.onload = () => resolve(); script.onerror = () => { script.remove(); scriptPromise = null; reject(new Error("Could not load Google sign-in. Check your connection.")); };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export default function GoogleSignIn({ onCredential, disabled = false }: { onCredential: (credential: string) => Promise<void>; disabled?: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onCredential); callback.current = onCredential;
  const [error, setError] = useState(""); const [configured, setConfigured] = useState<boolean | null>(null);
  const [revision, setRevision] = useState(0); const [busy, setBusy] = useState(false);
  useEffect(() => { if (container.current) container.current.inert = disabled || busy; }, [disabled, busy]);
  useEffect(() => {
    let active = true;
    const start = async () => {
      const config = await api<{ enabled: boolean; client_id: string }>("/auth/google/config");
      if (!active) return; setConfigured(config.enabled);
      if (!config.enabled) return;
      const challenge = await api<{ nonce: string }>("/auth/google/challenge", { credentials: "include" });
      await loadGoogle();
      if (!active || !container.current || !window.google) return;
      window.google.accounts.id.initialize({ client_id: config.client_id, nonce: challenge.nonce, auto_select: false, callback: response => {
        if (!active) return; setBusy(true); setError("");
        void callback.current(response.credential).catch((err: Error) => { if (active) setError(err.message); }).finally(() => { if (active) { setBusy(false); setRevision(value => value + 1); } });
      } });
      container.current.replaceChildren();
      window.google.accounts.id.renderButton(container.current, { theme: "outline", size: "large", text: "continue_with", width: 280 });
    };
    void start().catch((err: Error) => { if (active) setError(err.message); });
    const expiry = window.setTimeout(() => { if (active) setRevision(value => value + 1); }, 240000);
    return () => { active = false; window.clearTimeout(expiry); };
  }, [revision]);
  return <div className="google-sign-in">
    <div ref={container} aria-disabled={disabled || busy} style={{ opacity: disabled || busy ? .5 : 1, pointerEvents: disabled || busy ? "none" : "auto" }} />
    {configured === false && <p className="muted">Google sign-in will be available once your administrator completes Google setup.</p>}
    {busy && <p className="muted" role="status">Signing in…</p>}
    {error && <p className="error" role="alert">{error} <button type="button" className="btn ghost small" onClick={() => setRevision(value => value + 1)}>Try again</button></p>}
  </div>;
}
