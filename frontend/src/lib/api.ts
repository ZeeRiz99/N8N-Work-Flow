// Typed client for the Replyline backend (P3 hand-written; P4 generates it from OpenAPI).
// 127.0.0.1 rather than localhost: on Windows, localhost tries IPv6 first.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
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

export const api = {
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
