import type { PlatformAuth, TenantSession } from "./types";
import { isMobileDevice } from "./pwa";

const TENANT_KEY = "hrms_tenant_token";
const TENANT_REFRESH_KEY = "hrms_tenant_refresh";
const ADMIN_KEY = "hrms_platform_token";
const ADMIN_REFRESH_KEY = "hrms_platform_refresh";
const SESSION_KEY = "hrms_tenant_session";
const ADMIN_SESSION_KEY = "hrms_platform_session";

type TokenPair = {
  access_token: string;
  refresh_token: string;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0] && typeof detail[0].msg === "string") {
    return detail[0].msg;
  }
  return "Request failed";
}

function parseBody<T>(text: string, status: number): T & { detail?: unknown } {
  try {
    return (text ? JSON.parse(text) : {}) as T & { detail?: unknown };
  } catch {
    const looksLikePage = /^\s*</.test(text);
    throw new Error(
      looksLikePage || status >= 500
        ? "The API is not reachable. Refresh the page, or wait for the backend to finish starting."
        : text || "Request failed",
    );
  }
}

function refreshKind(path: string): "tenant" | "platform" | null {
  if (
    path === "/domains/context"
    || path.startsWith("/auth/login")
    || ["/auth/google/login", "/auth/google/config", "/auth/google/challenge"].some(publicPath => path.startsWith(publicPath))
    || path.startsWith("/auth/register")
    || path.startsWith("/auth/refresh")
    || path.startsWith("/platform/auth/")
  ) {
    return null;
  }
  if (path.startsWith("/platform")) return "platform";
  return "tenant";
}

export const tenantToken = {
  get: () => localStorage.getItem(TENANT_KEY),
  set: (token: string, refresh?: string) => {
    localStorage.setItem(TENANT_KEY, token);
    if (refresh) localStorage.setItem(TENANT_REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(TENANT_KEY);
    localStorage.removeItem(TENANT_REFRESH_KEY);
  },
};

export const adminToken = {
  get: () => localStorage.getItem(ADMIN_KEY),
  set: (token: string, refresh?: string) => {
    localStorage.setItem(ADMIN_KEY, token);
    if (refresh) localStorage.setItem(ADMIN_REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(ADMIN_KEY);
    localStorage.removeItem(ADMIN_REFRESH_KEY);
  },
};

const refreshLocks: { tenant: Promise<string | null> | null; platform: Promise<string | null> | null } = {
  tenant: null,
  platform: null,
};

async function refreshAccess(kind: "tenant" | "platform"): Promise<string | null> {
  if (refreshLocks[kind]) return refreshLocks[kind];
  refreshLocks[kind] = (async () => {
    const refresh = kind === "platform"
      ? localStorage.getItem(ADMIN_REFRESH_KEY)
      : localStorage.getItem(TENANT_REFRESH_KEY);
    const path = kind === "platform" ? "/platform/auth/refresh" : "/auth/refresh";
    if (!refresh) return null;
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      const text = await response.text();
      const body = parseBody<TokenPair>(text, response.status);
      if (!response.ok) throw new Error(detailMessage(body.detail));
      if (kind === "platform") adminToken.set(body.access_token, body.refresh_token);
      else tenantToken.set(body.access_token, body.refresh_token);
      return body.access_token;
    } catch {
      if (kind === "platform") {
        adminToken.clear();
        adminSession.clear();
      } else {
        tenantToken.clear();
        tenantSession.clear();
      }
      return null;
    } finally {
      refreshLocks[kind] = null;
    }
  })();
  return refreshLocks[kind];
}

function storedToken(kind: "tenant" | "platform" | null): string | null {
  if (kind === "platform") return adminToken.get();
  if (kind === "tenant") return tenantToken.get();
  return null;
}

async function authorizedFetch(path: string, init: RequestInit, token?: string | null): Promise<Response> {
  const kind = refreshKind(path);
  const used = storedToken(kind) || token || null;
  const headers = new Headers(init.headers);
  headers.set("ngrok-skip-browser-warning", "true");
  if (used) headers.set("Authorization", `Bearer ${used}`);
  let response = await fetch(path, { ...init, headers });
  if (response.status === 401 && kind) {
    const next = await refreshAccess(kind);
    if (next) {
      const retryHeaders = new Headers(init.headers);
      retryHeaders.set("ngrok-skip-browser-warning", "true");
      retryHeaders.set("Authorization", `Bearer ${next}`);
      response = await fetch(path, { ...init, headers: retryHeaders });
    }
  }
  return response;
}

export async function api<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, headers, ...rest } = options;
  const response = await authorizedFetch(path, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  }, token);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const body = parseBody<T>(text, response.status);
  if (!response.ok) {
    throw new Error(detailMessage(body.detail));
  }
  return body;
}

export async function apiUploadForm<T>(path: string, body: FormData, token: string): Promise<T> {
  const response = await authorizedFetch(path, { method: "POST", body }, token);
  const text = await response.text();
  const parsed = parseBody<T>(text, response.status);
  if (!response.ok) throw new Error(detailMessage(parsed.detail));
  return parsed;
}

export async function apiUpload<T>(path: string, file: File, token: string): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const response = await authorizedFetch(path, { method: "PUT", body }, token);
  const text = await response.text();
  const parsed = parseBody<T>(text, response.status);
  if (!response.ok) throw new Error(detailMessage(parsed.detail));
  return parsed;
}

export async function apiUploadFiles<T>(path: string, files: File[], token: string): Promise<T> {
  const body = new FormData();
  for (const file of files) body.append("files", file);
  const response = await authorizedFetch(path, { method: "POST", body }, token);
  const text = await response.text();
  const parsed = parseBody<T>(text, response.status);
  if (!response.ok) throw new Error(detailMessage(parsed.detail));
  return parsed;
}

export async function apiBlob(path: string, token: string): Promise<string | null> {
  const response = await authorizedFetch(path, {}, token);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Could not load file");
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

function fileMime(filename: string, type: string): string {
  const lower = (type || "").split(";")[0].trim().toLowerCase();
  if (lower && lower !== "application/octet-stream" && !lower.includes("text/html")) return lower;
  const name = filename.toLowerCase();
  if (name.endsWith(".pdf")) return "application/pdf";
  if (name.endsWith(".png")) return "image/png";
  if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
  if (name.endsWith(".webp")) return "image/webp";
  if (name.endsWith(".gif")) return "image/gif";
  if (name.endsWith(".txt")) return "text/plain";
  if (name.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (name.endsWith(".doc")) return "application/msword";
  return lower || "application/octet-stream";
}

export async function apiFileBlob(
  path: string,
  token: string,
  filename = "",
): Promise<{ url: string; type: string; blob: Blob }> {
  const response = await authorizedFetch(path, {}, token);
  if (!response.ok) throw new Error("Could not open document");
  const raw = await response.blob();
  if ((raw.type || "").includes("text/html")) throw new Error("Could not open document");
  const type = fileMime(filename, raw.type || response.headers.get("content-type") || "");
  const blob = raw.type === type ? raw : new Blob([await raw.arrayBuffer()], { type });
  return { url: URL.createObjectURL(blob), type, blob };
}

export async function apiDownload(path: string, token: string, filename: string): Promise<void> {
  const file = await apiFileBlob(path, token, filename);
  const link = document.createElement("a");
  link.href = file.url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(file.url), 60_000);
}

export function viewDocument(
  path: string,
  token: string,
  filename: string,
  onPreview: () => void,
): void {
  if (!isMobileDevice()) {
    onPreview();
    return;
  }
  const popup = window.open("about:blank", "_blank");
  void apiFileBlob(path, token, filename)
    .then((file) => {
      if (popup && !popup.closed) {
        popup.location.replace(file.url);
        window.setTimeout(() => URL.revokeObjectURL(file.url), 60_000);
        return;
      }
      URL.revokeObjectURL(file.url);
      onPreview();
    })
    .catch(() => {
      popup?.close();
      onPreview();
    });
}

export const tenantSession = {
  get(): TenantSession | null {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as TenantSession;
    } catch {
      return null;
    }
  },
  set(value: TenantSession) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(value));
  },
  patch(partial: Partial<TenantSession>) {
    const current = tenantSession.get();
    if (!current) return;
    tenantSession.set({ ...current, ...partial });
  },
  clear() {
    localStorage.removeItem(SESSION_KEY);
  },
};

export function apiUrl(apiBase: string | undefined, path: string): string {
  const prefix = apiBase ?? "";
  return `${prefix}${path.startsWith("/") ? path : `/${path}`}`;
}

export const adminSession = {
  get(): PlatformAuth["admin"] | null {
    const raw = localStorage.getItem(ADMIN_SESSION_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as PlatformAuth["admin"];
    } catch {
      return null;
    }
  },
  set(value: PlatformAuth["admin"]) {
    localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(value));
  },
  clear() {
    localStorage.removeItem(ADMIN_SESSION_KEY);
  },
};
