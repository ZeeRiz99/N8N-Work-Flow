// Typed client for the Replyline backend. Calls are same-origin (/api/* is proxied to FastAPI by
// next.config.ts), so the httpOnly session cookies travel automatically and never touch JS.
// Types marked "generated" come from FastAPI's OpenAPI schema (npm run gen:api).
import type { components } from "./api-schema";

export const API_BASE = "";
const CSRF_HEADER = { "X-Requested-With": "replyline" };

type Schemas = components["schemas"];
export type Me = Schemas["MeOut"]; // generated
export type Org = Schemas["OrgOut"]; // generated
export type Member = Schemas["MemberOut"]; // generated
export type Stage = Schemas["StageOut"]; // generated
export type Source = Schemas["SourceOut"]; // generated
export type Service = Schemas["ServiceOut"]; // generated

export type Priority = "high" | "medium" | "low" | "unscored";
export type AiStatus = "pending" | "processing" | "done" | "failed" | "skipped";

// Lead endpoints return plain JSON for now (backlog #20: add response models, then generate).
export interface LeadRow {
  id: string;
  full_name: string;
  company: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  priority: Priority;
  score: number | null;
  score_source: string | null;
  ai_status: AiStatus;
  stage: { id: string | null; key: string | null; label: string | null };
  source: string | null;
  assigned_to: { id: string; name: string | null } | null;
  do_not_contact: boolean;
  archived: boolean;
  inquiries: number;
  latest_message: string;
  created_at: string;
  last_interaction_at: string;
  merged?: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Note {
  id: string;
  body: string;
  author: string | null;
  created_at: string;
}

export interface Activity {
  id: string;
  type: string;
  actor_type: "user" | "system" | "workflow" | "ai";
  actor: string | null;
  payload: Record<string, string | number | null | string[]>;
  created_at: string;
}

export interface Inquiry {
  id: string;
  message: string;
  channel: string;
  form_fields: Record<string, string>;
  received_at: string;
}

export interface ImportReport {
  dry_run: boolean;
  columns: string[];
  mapping: Record<string, string>;
  total_rows: number;
  valid_rows: number;
  would_create: number;
  would_merge: number;
  created: number;
  merged: number;
  errors: { row: number; field: string; message: string }[];
  error_count: number;
}

export interface DuplicatePair {
  id: string;
  confidence: number;
  reasons: { field: string; similarity: number }[];
  leads: {
    id: string;
    full_name: string;
    company: string | null;
    email: string | null;
    phone: string | null;
    created_at: string;
  }[];
}

export interface FormConfig {
  organization_name: string;
  form_key: string;
  services: string[];
  budget_options: string[];
  timeline_options: string[];
  response_time_line: string;
}

export interface LeadFilters {
  q?: string;
  stage?: string;
  priority?: string;
  source?: string;
  assigned?: string;
  archived?: boolean;
  sort?: "recent" | "newest" | "score" | "name";
  page?: number;
  page_size?: number;
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

/** Thrown when the session is gone and the refresh token could not renew it. */
export class AuthRequired extends Error {
  constructor() {
    super("Please log in.");
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

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});
const json = (body: unknown) => send("POST", body);

function query(params: object): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

const lead = (id: string) => `/api/v1/leads/${encodeURIComponent(id)}`;

export const api = {
  // auth
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

  // organization
  org: () => request<Org>("/api/v1/org"),
  members: () => request<Member[]>("/api/v1/org/members"),
  stages: () => request<Stage[]>("/api/v1/settings/pipeline"),
  sources: () => request<Source[]>("/api/v1/settings/sources"),
  services: () => request<Service[]>("/api/v1/settings/services"),

  // leads
  leads: (filters: LeadFilters = {}) => request<Page<LeadRow>>(`/api/v1/leads${query(filters)}`),
  lead: (id: string) => request<LeadRow>(lead(id)),
  createLead: (body: {
    full_name: string;
    email?: string;
    phone?: string;
    company?: string;
    website?: string;
    message?: string;
  }) => request<LeadRow>("/api/v1/leads", json(body)),
  updateLead: (id: string, body: Record<string, unknown>) =>
    request<LeadRow>(lead(id), send("PATCH", body)),
  setStage: (id: string, stage_id: string) =>
    request<LeadRow>(`${lead(id)}/stage`, json({ stage_id })),
  assign: (id: string, user_id: string | null) =>
    request<LeadRow>(`${lead(id)}/assign`, json({ user_id })),
  archive: (id: string) => request<LeadRow>(`${lead(id)}/archive`, { method: "POST" }),
  restore: (id: string) => request<LeadRow>(`${lead(id)}/restore`, { method: "POST" }),
  erase: (id: string) => request<void>(lead(id), { method: "DELETE" }),
  notes: (id: string) => request<Note[]>(`${lead(id)}/notes`),
  addNote: (id: string, body: string) => request<Note>(`${lead(id)}/notes`, json({ body })),
  activities: (id: string) => request<Activity[]>(`${lead(id)}/activities`),
  inquiries: (id: string) => request<Inquiry[]>(`${lead(id)}/inquiries`),

  // data
  importCsv: (csv: string, dry_run: boolean, mapping?: Record<string, string>) =>
    request<ImportReport>("/api/v1/leads/import", json({ csv, dry_run, mapping })),
  exportUrl: "/api/v1/leads/export",
  duplicates: () => request<DuplicatePair[]>("/api/v1/duplicates"),
  scanDuplicates: () => request<{ added: number }>("/api/v1/duplicates/scan", { method: "POST" }),
  mergeDuplicate: (id: string, keep_lead_id: string) =>
    request<{ kept_lead_id: string }>(`/api/v1/duplicates/${id}/merge`, json({ keep_lead_id })),
  dismissDuplicate: (id: string) =>
    request<void>(`/api/v1/duplicates/${id}/dismiss`, { method: "POST" }),

  // public form
  formConfig: (slug: string) =>
    request<FormConfig>(`/api/v1/public/forms/${encodeURIComponent(slug)}`),
  submitLead: (formKey: string, body: Record<string, unknown>) =>
    request<{ status: string; reference: string }>("/api/v1/public/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Form-Key": formKey },
      body: JSON.stringify(body),
    }),
};

/** A short, safe message for any error, with the request id when the server gave one. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const rid = e.body?.error.request_id;
    return `${e.message}${rid ? ` (request ${rid})` : ""}`;
  }
  return "The server is not reachable. Please try again.";
}
