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
  score_provisional: boolean;
  needs_review: boolean;
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

export interface Quote {
  text?: string;
  name?: string;
  evidence: string | null;
  source?: "message" | "form";
}

export interface Facts {
  services: Quote[];
  budget: {
    min_minor: number | null;
    max_minor: number | null;
    currency: string;
    comparable: boolean;
    evidence: string | null;
    source: "message" | "form";
  } | null;
  timeline: {
    text: string | null;
    urgency: string;
    evidence: string | null;
    source: string | null;
  };
  company: string | null;
  industry: string | null;
  requirements: Quote[];
  buying_signals: Quote[];
  missing_info: string[];
  rejected: { field: string; reason: string }[];
  conflicts: string[];
}

export interface Factor {
  key: string;
  label: string;
  points: number;
  max: number;
  reason: string;
  evidence: string | null;
}

export interface LeadAnalysis {
  analysis: {
    id: string;
    status: "done" | "failed" | "skipped";
    error: string | null;
    provider: string;
    model: string | null;
    prompt_version: string;
    latency_ms: number | null;
    created_at: string;
    facts: Facts;
    intent: string | null;
    red_flags: string[];
    summary: string | null;
    recommended_next_action: string | null;
    guard_flags: string[];
  } | null;
  score: {
    total: number;
    band: Priority;
    factors: Factor[];
    explanation: string;
    caps: string[];
    provisional: boolean;
    needs_review: boolean;
    config_version: number;
    created_at: string;
  } | null;
}

export interface DraftCheck {
  key: string;
  label: string;
  ok: boolean;
  severity: "fail" | "warn";
  detail: string;
}

export interface Draft {
  to: string | null;
  subject: string;
  body: string;
  questions: string[];
  services_mentioned: string[];
  style: string;
  source: string;
  model: string | null;
  prompt_version: string;
  note: string | null;
  checks: DraftCheck[];
  all_passed: boolean;
}

export interface AskResult {
  answer: string;
  refused: boolean;
  citations: { id: string; kind: string; label: string }[];
  removed_citations: number;
  supported: boolean;
  source: string;
  model: string | null;
  note: string | null;
}

export interface FollowUpStatus {
  eligible: boolean;
  checks: { key: string; label: string; ok: boolean }[];
  next_possible: string | null;
  replies_tracked: boolean;
}

export interface PlaygroundResult {
  facts: Facts;
  intent: string | null;
  summary: string | null;
  guard_flags: string[];
  score: {
    total: number;
    band: Priority;
    explanation: string;
    factors: Omit<Factor, "label">[];
    caps: string[];
    provisional: boolean;
  };
  needs_review: boolean;
  source: string | null;
  model: string | null;
  note: string | null;
  saved: boolean;
}

export interface AISettings {
  default_style: string;
  daily_cap: number;
  server_max_daily_cap: number;
  provider: string;
  model: string;
}

export interface SavedDraft {
  id: string;
  lead_id: string;
  lead_name: string | null;
  lead_company: string | null;
  lead_score: number | null;
  lead_priority: Priority | null;
  kind: "first_reply" | "follow_up";
  to: string | null;
  subject: string;
  body: string;
  style: string;
  status: string;
  checks: DraftCheck[];
  all_passed: boolean;
  source: string;
  model: string | null;
  edited: boolean;
  rejection_reason: string | null;
  send_error: string | null;
  created_at: string;
  approved_at: string | null;
  sent_at: string | null;
  note?: string | null;
}

export interface AutomationOverview {
  n8n: { ok: boolean; detail: string; editor_url: string };
  workflows: {
    key: string;
    name: string;
    purpose: string;
    runs_7d: number;
    success_7d: number;
    skipped_7d: number;
    failed_7d: number;
    last_status: string | null;
    last_run_at: string | null;
  }[];
  journey: { key: string; label: string; count: number }[];
  outbox: { pending: number; failed: number };
  recent: {
    workflow_key: string;
    status: string;
    n8n_execution_id: string;
    request_id: string | null;
    lead_id: string | null;
    error: string | null;
    meta: Record<string, string | number | boolean | null>;
    created_at: string;
  }[];
}

export interface Integration {
  kind: string;
  name: string;
  configured: boolean;
  detail: string;
}

export interface OverviewData {
  days: number;
  cards: {
    new_leads: number;
    new_leads_previous: number;
    high_priority: number;
    awaiting_approval: number;
    median_first_reply_minutes: number | null;
    answered_leads: number;
    reply_target_minutes: number;
  };
  priority_mix: { priority: Priority; count: number; share: number }[];
  stages: { label: string; category: string; count: number }[];
  automation_week: { runs: number; emails_sent: number; alerts: number };
  latest: {
    id: string;
    full_name: string;
    company: string | null;
    priority: Priority;
    score: number | null;
    ai_status: string;
    next_step: string;
    last_interaction_at: string;
  }[];
}

export interface TrendPoint {
  date: string;
  leads: number;
  high: number;
}

export interface FollowUpItem {
  id: string;
  lead_id: string;
  lead_name: string | null;
  lead_company: string | null;
  lead_priority: Priority | null;
  due_at: string;
  status: string;
  attempt_no: number;
  skip_reason: string | null;
  draft_id: string | null;
  completed_at: string | null;
}

export interface ContactRules {
  allowed: boolean;
  checks: { key: string; label: string; ok: boolean }[];
  next_follow_up_at: string | null;
}

export interface MergePreview {
  keep_id: string;
  drop_id: string;
  fields: {
    field: string;
    keep: string | null;
    other: string | null;
    result: string | null;
    source: string;
  }[];
  moves: { messages: number; notes: number; timeline_entries: number };
  do_not_contact: boolean;
}

export interface SourceRow {
  source: string;
  leads: number;
  high: number;
  won: number;
  conversion: number;
  median_score: number | null;
}

export interface FunnelData {
  days: number;
  total: number;
  lost: number;
  win_rate: number;
  steps: { key: string; label: string; reached: number; from_previous: number }[];
}

export interface TeamRow {
  user_id: string;
  name: string;
  role: string;
  assigned: number;
  approved: number;
  sent: number;
  won: number;
}

export interface ReportSnapshot {
  id: string;
  kind: "daily" | "source_performance";
  period_start: string;
  period_end: string;
  metrics: Record<string, unknown>;
  narrative: string;
  narrative_source: "ai" | "template";
  validation: Record<string, unknown>;
  created_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
  link?: string;
  emailed?: boolean;
}

export interface NotificationSettings {
  alert_on_high: boolean;
  daily_report: boolean;
  weekly_report: boolean;
  alert_email: string | null;
}

export interface ScorePreviewRow {
  lead_id: string;
  name: string;
  old_score: number;
  old_band: Priority;
  new_score: number;
  new_band: Priority;
}

export interface ScoringConfig {
  version: number;
  weights: Record<string, number>;
  thresholds: { high_min: number; medium_min: number };
  ideal_industries: string[];
  labels: Record<string, string>;
  defaults: {
    weights: Record<string, number>;
    thresholds: { high_min: number; medium_min: number };
  };
  updated_at: string;
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
  analysis: (id: string) => request<LeadAnalysis>(`${lead(id)}/analysis`),
  reanalyze: (id: string) => request<unknown>(`${lead(id)}/reanalyze`, { method: "POST" }),
  scoring: () => request<ScoringConfig>("/api/v1/settings/scoring"),
  analyticsSources: (days: number) =>
    request<{ days: number; rows: SourceRow[] }>(`/api/v1/analytics/sources?days=${days}`),
  analyticsFunnel: (days: number) => request<FunnelData>(`/api/v1/analytics/funnel?days=${days}`),
  analyticsTeam: (days: number) =>
    request<{ days: number; rows: TeamRow[] }>(`/api/v1/analytics/team?days=${days}`),
  analyticsExportUrl: (days: number) => `/api/v1/analytics/export?days=${days}`,
  reports: () => request<ReportSnapshot[]>("/api/v1/analytics/reports"),
  makeReport: (kind: string) =>
    request<ReportSnapshot>(`/api/v1/analytics/reports/${kind}`, { method: "POST" }),
  invitations: () => request<Invitation[]>("/api/v1/org/invitations"),
  invite: (email: string, role: string) =>
    request<Invitation>("/api/v1/org/invitations", json({ email, role })),
  revokeInvite: (id: string) =>
    request<void>(`/api/v1/org/invitations/${id}`, { method: "DELETE" }),
  invitationInfo: (token: string) =>
    request<{ organization_name: string; email: string; role: string; has_account: boolean }>(
      `/api/v1/auth/invitations/${encodeURIComponent(token)}`,
    ),
  acceptInvite: (token: string, full_name: string, password: string) =>
    request<Me>(
      `/api/v1/auth/invitations/${encodeURIComponent(token)}/accept`,
      json({ full_name, password }),
    ),
  updateMember: (id: string, role: string) =>
    request<Member>(`/api/v1/org/members/${id}`, send("PATCH", { role })),
  removeMember: (id: string) => request<void>(`/api/v1/org/members/${id}`, { method: "DELETE" }),
  addStage: (label: string, category: string) =>
    request<Stage>("/api/v1/settings/pipeline", json({ label, category })),
  updateStage: (id: string, body: { label?: string; position?: number }) =>
    request<Stage>(`/api/v1/settings/pipeline/${id}`, send("PATCH", body)),
  deleteStage: (id: string) =>
    request<void>(`/api/v1/settings/pipeline/${id}`, { method: "DELETE" }),
  notifications: () => request<NotificationSettings>("/api/v1/settings/notifications"),
  saveNotifications: (body: NotificationSettings) =>
    request<NotificationSettings>("/api/v1/settings/notifications", send("PUT", body)),
  retention: () =>
    request<{ erase_archived_after_days: number | null; due_for_erasure: number }>(
      "/api/v1/settings/retention",
    ),
  saveRetention: (days: number | null) =>
    request<{ erase_archived_after_days: number | null; due_for_erasure: number }>(
      "/api/v1/settings/retention",
      send("PUT", { erase_archived_after_days: days }),
    ),
  purgeArchived: () =>
    request<{ erased: number }>("/api/v1/settings/retention/purge", { method: "POST" }),
  followUpSettings: () =>
    request<{
      max_attempts: number;
      cooldown_days: number;
      timezone: string;
      business_hours: string;
    }>("/api/v1/settings/follow-ups"),
  saveFollowUpSettings: (max_attempts: number, cooldown_days: number) =>
    request<{ max_attempts: number; cooldown_days: number }>(
      "/api/v1/settings/follow-ups",
      send("PUT", { max_attempts, cooldown_days }),
    ),
  scoringPreview: (weights: Record<string, number>, thresholds: Record<string, number>) =>
    request<{ rows: ScorePreviewRow[]; band_changes: number }>(
      "/api/v1/settings/scoring/preview",
      json({ weights, thresholds }),
    ),
  followUps: (status: string) => request<FollowUpItem[]>(`/api/v1/follow-ups${query({ status })}`),
  prepareFollowUp: (id: string) =>
    request<{ status: string; reason?: string }>(`/api/v1/follow-ups/${id}/prepare`, {
      method: "POST",
    }),
  skipFollowUp: (id: string, reason: string) =>
    request<{ status: string }>(`/api/v1/follow-ups/${id}/skip`, json({ reason })),
  scheduleFollowUp: (id: string, due_at: string) =>
    request<FollowUpItem>(`${lead(id)}/follow-ups`, json({ due_at })),
  markReplied: (id: string) => request<{ ok: boolean }>(`${lead(id)}/replied`, json({})),
  optOut: (id: string) => request<{ ok: boolean }>(`${lead(id)}/opt-out`, { method: "POST" }),
  contactRules: (id: string) => request<ContactRules>(`${lead(id)}/contact-rules`),
  mergePreview: (pairId: string, keep: string) =>
    request<MergePreview>(`/api/v1/duplicates/${pairId}/preview${query({ keep })}`),
  overview: (days: number) => request<OverviewData>(`/api/v1/analytics/overview?days=${days}`),
  trends: (days: number) =>
    request<{ days: number; series: TrendPoint[] }>(`/api/v1/analytics/trends?days=${days}`),
  automation: () => request<AutomationOverview>("/api/v1/automation/overview"),
  redispatch: () =>
    request<{ requeued: number }>("/api/v1/automation/outbox/redispatch", { method: "POST" }),
  integrations: () => request<Integration[]>("/api/v1/integrations"),
  testIntegration: (kind: string) =>
    request<{ ok: boolean; detail: string }>(`/api/v1/integrations/${kind}/test`, {
      method: "POST",
    }),
  drafts: (status = "pending_approval", leadId?: string) =>
    request<SavedDraft[]>(`/api/v1/drafts${query({ status, lead_id: leadId })}`),
  saveDraft: (id: string, kind = "first_reply", style: string | null = null) =>
    request<SavedDraft>(`${lead(id)}/drafts`, json({ kind, style })),
  editDraft: (id: string, subject: string, body: string) =>
    request<SavedDraft>(`/api/v1/drafts/${id}`, send("PATCH", { subject, body })),
  approveDraft: (id: string) =>
    request<SavedDraft>(`/api/v1/drafts/${id}/approve`, { method: "POST" }),
  rejectDraft: (id: string, reason: string) =>
    request<SavedDraft>(`/api/v1/drafts/${id}/reject`, json({ reason })),
  rescore: () =>
    request<{ changed: number; version: number }>("/api/v1/settings/scoring/rescore", {
      method: "POST",
    }),
  generateDraft: (id: string, style: string | null, kind = "first_reply") =>
    request<Draft>(`${lead(id)}/drafts/generate`, json({ style, kind })),
  ask: (id: string, question: string) => request<AskResult>(`${lead(id)}/ask`, json({ question })),
  followUp: (id: string) => request<FollowUpStatus>(`${lead(id)}/follow-up`),
  analyzeText: (message: string) =>
    request<PlaygroundResult>("/api/v1/ai/analyze-text", json({ message })),
  aiSettings: () => request<AISettings>("/api/v1/settings/ai"),
  saveAiSettings: (body: { default_style: string; daily_cap: number }) =>
    request<AISettings>("/api/v1/settings/ai", send("PUT", body)),
  checkDraft: (id: string, subject: string, body: string, services_mentioned: string[]) =>
    request<{ checks: DraftCheck[]; all_passed: boolean }>(
      `${lead(id)}/drafts/check`,
      json({ subject, body, services_mentioned }),
    ),
  sampleStatus: () =>
    request<{ available: boolean; sample_leads: number }>("/api/v1/org/sample-data"),
  loadSample: (count: number) =>
    request<{ leads: number; duplicate_pairs: number; sample_leads: number }>(
      "/api/v1/org/sample-data",
      json({ count }),
    ),
  clearSample: () => request<{ removed: number }>("/api/v1/org/sample-data", { method: "DELETE" }),
  saveScoring: (body: {
    weights: Record<string, number>;
    thresholds: { high_min: number; medium_min: number };
    ideal_industries: string[];
  }) => request<ScoringConfig>("/api/v1/settings/scoring", send("PUT", body)),

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
