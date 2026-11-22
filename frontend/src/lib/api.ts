// Typed client for the Replyline backend. Calls are same-origin (/api/* is proxied to FastAPI by
// next.config.ts), so the httpOnly session cookies travel automatically and never touch JS.
export const API_BASE = "";
const CSRF_HEADER = { "X-Requested-With": "replyline" };

export interface Me {
  user_id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "member";
  organization_id: string;
  organization_name: string;
  organization_slug: string;
}

/** Thrown when the session is gone and the refresh token could not renew it. */
export class AuthRequired extends Error {
  constructor() {
    super("Please log in.");
  }
}

export type Priority = "high" | "medium" | "low" | "unscored";
export type AiStatus = "pending" | "processing" | "done" | "failed" | "skipped";

export interface LeadRow {
  id: string;
  full_name: string;
  company: string | null;
  email: string | null;
  priority: Priority;
  score: number | null;
  score_source: string | null;
  ai_status: AiStatus;
  inquiries: number;
  latest_message: string;
  created_at: string;
  last_interaction_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface FormConfig {
  organization_name: string;
  form_key: string;
  services: string[];
  budget_options: string[];
  timeline_options: string[];
  response_time_line: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { field: string; message: string }[] | null;
    request_id: string;
  };
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody | null,
  ) {
    super(body?.error.message ?? `Request failed (${status})`);
  }
}

let refreshing: Promise<boolean> | null = null;

/** One shared refresh at a time, however many requests hit 401 together. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: CSRF_HEADER,
    credentials: "same-origin",
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = { ...(method === "GET" ? {} : CSRF_HEADER), ...init?.headers };
  const resp = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
    headers,
  });
  // Login, sign-up and refresh answer 401 for wrong credentials; only other calls try a refresh.
  const isCredentialCall = /^\/api\/v1\/auth\/(login|register|refresh|logout)$/.test(path);
  if (resp.status === 401 && !isCredentialCall) {
    if (!retried && (await refreshSession())) return request<T>(path, init, true);
    throw new AuthRequired();
  }
  if (resp.status === 204) return undefined as T;
  if (!resp.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await resp.json()) as ApiErrorBody;
    } catch {
      body = null;
    }
    throw new ApiError(resp.status, body);
  }
  return (await resp.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  me: () => request<Me>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    request<Me>("/api/v1/auth/login", json({ email, password })),
  register: (body: {
    organization_name: string;
    full_name: string;
    email: string;
    password: string;
  }) => request<Me>("/api/v1/auth/register", json(body)),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  leads: (page = 1) => request<Page<LeadRow>>(`/api/v1/leads?page=${page}`),
  formConfig: (slug: string) =>
    request<FormConfig>(`/api/v1/public/forms/${encodeURIComponent(slug)}`),
  submitLead: (formKey: string, body: Record<string, unknown>) =>
    request<{ status: string; reference: string }>("/api/v1/public/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Form-Key": formKey },
      body: JSON.stringify(body),
    }),
};
