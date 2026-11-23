"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { AnalysisPanel, ScorePanel, sourceLabel } from "./ai-panels";
import { DraftPanel } from "./draft-panel";
import { AskPanel } from "@/components/ask-panel";
import { AiStatusPill, PriorityBadge } from "@/components/badges";
import { useSession } from "@/components/session";
import {
  buttonDanger,
  buttonPrimary,
  buttonSecondary,
  card,
  field,
  timeAgo,
} from "@/components/ui-tokens";
import {
  type Activity,
  api,
  ApiError,
  errorText,
  type Inquiry,
  type LeadAnalysis,
  type LeadRow,
  type Member,
  type Note,
  type Stage,
} from "@/lib/api";

function describe(a: Activity): string {
  const p = a.payload;
  switch (a.type) {
    case "lead_created":
      return `Lead created (${p.source ?? "unknown source"})`;
    case "lead_merged":
      return p.merged_lead ? "Merged with a duplicate lead" : "Matched an existing lead";
    case "inquiry_received":
      return `Message received (${p.channel})`;
    case "scored":
      return `Scored ${p.score}, ${p.band} priority${p.provisional ? " (provisional)" : ""}`;
    case "reanalysis_requested":
      return "Re-analysis requested";
    case "question_asked":
      return "Question asked about this lead";
    case "follow_up_drafted":
      return `Follow-up draft written (${p.style})`;
    case "draft_generated":
      return `Reply draft written (${p.style})`;
    case "rescored":
      return `Re-scored ${p.from_score ?? "?"} → ${p.score}`;
    case "stage_changed":
      return `Moved to ${p.to_label ?? p.to_stage}`;
    case "assigned":
      return "Assigned";
    case "unassigned":
      return "Unassigned";
    case "note_added":
      return "Note added";
    case "lead_updated":
      return `Details edited (${Array.isArray(p.fields) ? p.fields.join(", ") : ""})`;
    case "archived":
      return "Archived";
    case "restored":
      return "Restored";
    default:
      return a.type.replaceAll("_", " ");
  }
}

function who(a: Activity): string {
  if (a.actor_type === "ai") return "AI";
  if (a.actor_type === "system") return "Replyline";
  if (a.actor_type === "workflow") return "Automation";
  return a.actor ?? "Someone";
}

export function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const me = useSession();
  const [lead, setLead] = useState<LeadRow | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [analysis, setAnalysis] = useState<LeadAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [l, n, a, i, an] = await Promise.all([
        api.lead(id),
        api.notes(id),
        api.activities(id),
        api.inquiries(id),
        api.analysis(id),
      ]);
      setAnalysis(an);
      setLead(l);
      setNotes(n);
      setActivity(a);
      setInquiries(i);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
      else setError(errorText(e));
    }
  }, [id]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    Promise.all([api.stages(), api.members()])
      .then(([s, m]) => {
        setStages(s);
        setMembers(m);
      })
      .catch(() => undefined);
    return () => clearTimeout(t);
  }, [load]);

  // Keep refreshing while the AI works on this lead.
  const busy = lead?.ai_status === "pending" || lead?.ai_status === "processing";
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [busy, load]);

  async function act(fn: () => Promise<unknown>, message: string) {
    try {
      await fn();
      setToast(message);
      await load();
    } catch (e) {
      setToast(errorText(e));
    }
  }

  if (notFound) {
    return (
      <div className={`${card} p-8 text-center`}>
        <p className="font-semibold">Lead not found</p>
        <p className="mt-1 text-sm text-[#5A6075]">
          It may have been erased, or the link is wrong.
        </p>
        <Link href="/leads" className={`${buttonSecondary} mt-4`}>
          Back to leads
        </Link>
      </div>
    );
  }
  if (error && !lead) {
    return (
      <div role="alert" className="rounded-xl border border-[#F2C2B5] bg-[#FEF6F3] p-5">
        <p className="font-semibold text-[#A32A12]">Could not load this lead</p>
        <p className="mt-1 text-sm">{error}</p>
        <button type="button" onClick={load} className={`${buttonSecondary} mt-3`}>
          Try again
        </button>
      </div>
    );
  }
  if (!lead) return <div aria-busy="true" className="h-64 animate-pulse rounded-xl bg-[#E9ECF4]" />;

  const isAdmin = me.role === "owner" || me.role === "admin";

  return (
    <div className="flex flex-col gap-6">
      <div aria-live="polite" className="sr-only">
        {toast}
      </div>
      {toast && (
        <div
          role="status"
          className="flex items-center justify-between gap-3 rounded-lg bg-[#1A1D2B] px-4 py-2.5 text-sm text-white"
        >
          <span>{toast}</span>
          <button type="button" className="font-semibold underline" onClick={() => setToast(null)}>
            Dismiss
          </button>
        </div>
      )}

      <header className="flex flex-col gap-3">
        <nav aria-label="Breadcrumb" className="text-[13px] text-[#5A6075]">
          <Link href="/leads" className="no-underline">
            Leads
          </Link>{" "}
          / <span>{lead.full_name}</span>
        </nav>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-[26px] leading-tight font-bold tracking-tight">
                {lead.full_name}
              </h1>
              <PriorityBadge priority={lead.priority} />
              {lead.score !== null && (
                <span className="text-sm font-semibold tabular-nums">
                  Score {lead.score}
                  {sourceLabel(lead.score_source, lead.score_provisional) && (
                    <span className="ml-1 font-normal text-[#5A6075]">
                      ({sourceLabel(lead.score_source, lead.score_provisional)})
                    </span>
                  )}
                </span>
              )}
              <AiStatusPill status={lead.ai_status} />
              {lead.archived && (
                <span className="rounded-full bg-[#EDEDED] px-2.5 py-0.5 text-xs font-semibold text-[#3F3F3F]">
                  Archived
                </span>
              )}
            </div>
            <p className="text-[#5A6075]">
              {[lead.company, lead.email, lead.source].filter(Boolean).join(" · ")}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="stage" className="text-xs font-semibold text-[#3A4057]">
                Stage
              </label>
              <select
                id="stage"
                className={field}
                value={lead.stage.id ?? ""}
                onChange={(e) => act(() => api.setStage(lead.id, e.target.value), "Stage updated.")}
              >
                {stages.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="assignee" className="text-xs font-semibold text-[#3A4057]">
                Assigned to
              </label>
              <select
                id="assignee"
                className={field}
                value={lead.assigned_to?.id ?? ""}
                onChange={(e) =>
                  act(() => api.assign(lead.id, e.target.value || null), "Assignment updated.")
                }
              >
                <option value="">Unassigned</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name}
                  </option>
                ))}
              </select>
            </div>
            {lead.archived ? (
              <button
                type="button"
                className={buttonSecondary}
                onClick={() => act(() => api.restore(lead.id), "Lead restored.")}
              >
                Restore
              </button>
            ) : (
              <button
                type="button"
                className={buttonSecondary}
                onClick={() => act(() => api.archive(lead.id), "Lead archived.")}
              >
                Archive
              </button>
            )}
            {isAdmin && (
              <EraseButton
                name={lead.full_name}
                onErase={async () => {
                  await api.erase(lead.id);
                  router.replace("/leads");
                }}
              />
            )}
          </div>
        </div>
      </header>

      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[3_1_520px] flex-col gap-6">
          {analysis && (
            <AnalysisPanel
              data={analysis}
              onReanalyze={async () => {
                await api.reanalyze(lead.id);
                setToast("Analysis updated.");
                await load();
              }}
            />
          )}
          <DraftPanel
            leadId={lead.id}
            disabled={
              lead.do_not_contact
                ? "This lead is marked do not contact."
                : !lead.email
                  ? "Add an email address to draft a reply."
                  : undefined
            }
          />
          <section className={`${card} flex flex-col gap-3 p-6`}>
            <h2 className="text-base font-semibold">Messages</h2>
            {inquiries.length === 0 ? (
              <p className="text-sm text-[#5A6075]">No messages yet.</p>
            ) : (
              inquiries.map((i) => (
                <article key={i.id} className="rounded-lg bg-[#F6F7FB] p-4">
                  <div className="mb-1.5 flex flex-wrap justify-between gap-2 text-xs text-[#5A6075]">
                    <span>Via {i.channel}</span>
                    <time dateTime={i.received_at}>{new Date(i.received_at).toLocaleString()}</time>
                  </div>
                  {/* Customer text is rendered as plain text, never as HTML. */}
                  <p className="max-w-[68ch] leading-relaxed whitespace-pre-wrap">{i.message}</p>
                  {Object.keys(i.form_fields).length > 0 && (
                    <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-[#3A4057]">
                      {Object.entries(i.form_fields).map(([k, v]) => (
                        <div key={k} className="flex gap-1">
                          <dt className="capitalize">{k}:</dt>
                          <dd className="font-semibold">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </article>
              ))
            )}
          </section>
          <Notes leadId={lead.id} notes={notes} onAdded={load} />
        </div>

        <div className="flex min-w-0 flex-[2_1_320px] flex-col gap-6">
          {analysis && <ScorePanel data={analysis} />}
          <AskPanel leadId={lead.id} compact />
          <ContactDetails lead={lead} onSaved={(m) => act(async () => undefined, m)} />
          <section className={`${card} flex flex-col gap-3 p-5`}>
            <h2 className="text-base font-semibold">Timeline</h2>
            <ol className="flex flex-col">
              {activity.map((a, idx) => (
                <li key={a.id} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span
                      className={`mt-1.5 h-2.5 w-2.5 rounded-full ${idx === 0 ? "bg-[#4338CA]" : "bg-[#7B8299]"}`}
                    />
                    {idx < activity.length - 1 && <span className="w-0.5 flex-1 bg-[#E3E6EF]" />}
                  </div>
                  <div className="pb-3.5">
                    <div className="font-medium">{describe(a)}</div>
                    <div className="text-xs text-[#5A6075]">
                      {who(a)} · {timeAgo(a.created_at)}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}

function Notes({ leadId, notes, onAdded }: { leadId: string; notes: Note[]; onAdded: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = String(new FormData(form).get("body") ?? "").trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      await api.addNote(leadId, body);
      form.reset();
      onAdded();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={`${card} flex flex-col gap-3 p-6`}>
      <h2 className="text-base font-semibold">Notes</h2>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <label htmlFor="note-body" className="text-[13px] font-semibold">
          Add a note for your team
        </label>
        <textarea
          id="note-body"
          name="body"
          rows={3}
          maxLength={5000}
          placeholder="Only your team sees notes"
          className={`${field} py-2`}
        />
        {error && <p className="text-sm text-[#A32A12]">{error}</p>}
        <div>
          <button type="submit" disabled={busy} className={buttonSecondary}>
            {busy ? "Saving…" : "Save note"}
          </button>
        </div>
      </form>
      {notes.length === 0 ? (
        <p className="text-sm text-[#5A6075]">No notes yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {notes.map((n) => (
            <li key={n.id} className="rounded-lg border border-[#EEF0F6] p-3">
              <p className="whitespace-pre-wrap">{n.body}</p>
              <p className="mt-1 text-xs text-[#5A6075]">
                {n.author ?? "Former member"} · {timeAgo(n.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ContactDetails({ lead, onSaved }: { lead: LeadRow; onSaved: (msg: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => String(fd.get(k) ?? "").trim();
    try {
      await api.updateLead(lead.id, {
        full_name: v("full_name"),
        email: v("email") || null,
        phone: v("phone") || null,
        company: v("company") || null,
        website: v("website") || null,
        do_not_contact: fd.get("do_not_contact") === "on",
      });
      setEditing(false);
      setError(null);
      onSaved("Details saved.");
    } catch (err) {
      setError(errorText(err));
    }
  }
  const rows: [string, string | null][] = [
    ["Email", lead.email],
    ["Phone", lead.phone],
    ["Company", lead.company],
    ["Website", lead.website],
    ["Source", lead.source],
  ];
  return (
    <section className={`${card} flex flex-col gap-3 p-5`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Contact details</h2>
        {!editing && (
          <button type="button" className={buttonSecondary} onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <form onSubmit={submit} className="flex flex-col gap-3">
          {error && <p className="text-sm text-[#A32A12]">{error}</p>}
          {(
            [
              ["full_name", "Name", lead.full_name],
              ["email", "Email", lead.email],
              ["phone", "Phone", lead.phone],
              ["company", "Company", lead.company],
              ["website", "Website", lead.website],
            ] as const
          ).map(([name, label, value]) => (
            <div key={name} className="flex flex-col gap-1">
              <label htmlFor={`cd-${name}`} className="text-[13px] font-semibold">
                {label}
              </label>
              <input
                id={`cd-${name}`}
                name={name}
                defaultValue={value ?? ""}
                required={name === "full_name"}
                className={field}
              />
            </div>
          ))}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="do_not_contact"
              defaultChecked={lead.do_not_contact}
              className="h-5 w-5 accent-[#4338CA]"
            />
            Do not contact this lead
          </label>
          <div className="flex gap-2">
            <button type="submit" className={buttonPrimary}>
              Save
            </button>
            <button type="button" className={buttonSecondary} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <dl className="flex flex-col">
          {rows.map(([k, v]) => (
            <div
              key={k}
              className="flex justify-between gap-4 border-b border-[#EEF0F6] py-2.5 last:border-0"
            >
              <dt className="text-[#5A6075]">{k}</dt>
              <dd className={`text-right ${v ? "font-medium" : "text-[#5A6075] italic"}`}>
                {v ?? "Not provided"}
              </dd>
            </div>
          ))}
          {lead.do_not_contact && (
            <p className="pt-2 text-sm font-semibold text-[#8A3B00]">Marked do-not-contact.</p>
          )}
        </dl>
      )}
    </section>
  );
}

function EraseButton({ name, onErase }: { name: string; onErase: () => Promise<void> }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <button type="button" className={buttonDanger} onClick={() => ref.current?.showModal()}>
        Erase
      </button>
      <dialog
        ref={ref}
        aria-labelledby="erase-title"
        className="m-auto w-full max-w-md rounded-xl border border-[#E3E6EF] p-6 backdrop:bg-black/40"
      >
        <h2 id="erase-title" className="text-lg font-bold">
          Erase {name}?
        </h2>
        <p className="mt-2 text-sm text-[#3A4057]">
          This permanently deletes the lead, its messages, notes and timeline. An anonymous audit
          record stays. This cannot be undone.
        </p>
        {error && <p className="mt-2 text-sm text-[#A32A12]">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className={buttonSecondary} onClick={() => ref.current?.close()}>
            Keep the lead
          </button>
          <button
            type="button"
            className={buttonDanger}
            onClick={async () => {
              try {
                await onErase();
              } catch (e) {
                setError(errorText(e));
              }
            }}
          >
            Erase permanently
          </button>
        </div>
      </dialog>
    </>
  );
}
