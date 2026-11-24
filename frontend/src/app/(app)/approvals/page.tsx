"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { PriorityBadge } from "@/components/badges";
import { buttonDanger, buttonPrimary, buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, type DraftCheck, errorText, type LeadAnalysis, type SavedDraft } from "@/lib/api";

const KIND_LABEL: Record<string, string> = {
  first_reply: "First reply",
  follow_up: "Follow-up",
  recovery: "Check-in",
};
const OPT_OUT = `If you'd rather not hear from us again, just reply "unsubscribe".`;
const TABS = [
  ["pending_approval", "Waiting"],
  ["sent", "Sent"],
  ["failed", "Failed"],
  ["rejected", "Rejected"],
] as const;

function stripOptOut(body: string) {
  return body.replace(OPT_OUT, "").trimEnd();
}

function CheckList({ checks }: { checks: DraftCheck[] }) {
  return (
    <ul aria-label="Automatic checks" className="flex flex-col gap-1.5 text-sm">
      {checks.map((c) => {
        const color = c.ok ? "#1E6B3A" : c.severity === "warn" ? "#7A4A05" : "#A32A12";
        return (
          <li key={c.key} className="flex gap-2">
            <span aria-hidden="true" className="font-bold" style={{ color }}>
              {c.ok ? "✓" : c.severity === "warn" ? "!" : "✗"}
            </span>
            <span>
              <span className="sr-only">{c.ok ? "Passed: " : "Problem: "}</span>
              {c.label}
              {!c.ok && c.detail && <span className="text-[#5A6075]"> · {c.detail}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Context({ draft }: { draft: SavedDraft }) {
  const [data, setData] = useState<LeadAnalysis | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([api.analysis(draft.lead_id), api.inquiries(draft.lead_id)])
      .then(([a, inq]) => {
        if (!live) return;
        setData(a);
        setMessage(inq[0]?.message ?? null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [draft.lead_id]);
  const top = [...(data?.score?.factors ?? [])].sort((a, b) => b.points - a.points).slice(0, 3);
  return (
    <section aria-label="Lead context" className={`${card} flex flex-col gap-4 p-5`}>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">{draft.lead_name}</h2>
          {draft.lead_priority && <PriorityBadge priority={draft.lead_priority} />}
          {draft.lead_score !== null && (
            <span className="text-sm font-semibold tabular-nums">Score {draft.lead_score}</span>
          )}
        </div>
        <p className="text-sm text-[#5A6075]">{draft.lead_company ?? "No company given"}</p>
        <Link href={`/leads/${draft.lead_id}`} className="text-sm font-semibold text-[#4338CA]">
          Open lead →
        </Link>
      </div>
      {data?.analysis?.summary && (
        <p className="text-sm leading-relaxed">{data.analysis.summary}</p>
      )}
      {top.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-[#5A6075]">Top score factors</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {top.map((f) => (
              <li key={f.key} className="flex justify-between gap-2">
                <span>{f.label}</span>
                <span className="tabular-nums text-[#3A4057]">
                  {f.points}/{f.max}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {message && (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-[#5A6075]">Their message</h3>
          {/* Customer text is plain text, never HTML. */}
          <p className="rounded-lg bg-[#F6F7FB] p-3 text-sm leading-relaxed whitespace-pre-wrap">
            {message}
          </p>
        </div>
      )}
    </section>
  );
}

function Editor({ draft, onDone }: { draft: SavedDraft; onDone: (msg: string) => void }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(stripOptOut(draft.body));
  const [current, setCurrent] = useState(draft);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = subject !== current.subject || body !== stripOptOut(current.body);
  const open = current.status === "pending_approval";

  async function run(fn: () => Promise<SavedDraft>, done?: string) {
    setBusy(true);
    setError(null);
    try {
      const d = await fn();
      setCurrent(d);
      if (done) onDone(done);
      return d;
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (dirty) {
      const saved = await run(() => api.editDraft(current.id, subject, body));
      if (!saved || !saved.all_passed) return;
    }
    await run(() => api.approveDraft(current.id), "Approved. It is being sent now.");
  }

  const failing = current.checks.filter((c) => !c.ok && c.severity === "fail").length;

  return (
    <section
      aria-label="Draft"
      className={`${card} flex flex-col gap-4 p-5`}
      onKeyDown={(e) => {
        if (open && (e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          approve();
        }
      }}
    >
      <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold text-[#3A4057]">To</span>
        <span className="text-sm">{current.to ?? "No email address"}</span>
        <span className="text-xs text-[#5A6075]">
          From the lead record; cannot be changed here.
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="ap-subject" className="text-xs font-semibold text-[#3A4057]">
          Subject
        </label>
        <input
          id="ap-subject"
          className={field}
          value={subject}
          maxLength={200}
          disabled={!open}
          onChange={(e) => setSubject(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="ap-body" className="text-xs font-semibold text-[#3A4057]">
          Message
        </label>
        <textarea
          id="ap-body"
          rows={12}
          className={`${field} py-2 leading-relaxed`}
          value={body}
          maxLength={6000}
          disabled={!open}
          onChange={(e) => setBody(e.target.value)}
        />
        <p className="rounded-md bg-[#F6F7FB] px-3 py-2 text-xs text-[#5A6075]">
          <span aria-hidden="true">🔒 </span>Added automatically: {OPT_OUT}
        </p>
      </div>
      <div className="rounded-lg bg-[#F6F7FB] p-4">
        <h3 className="mb-2 text-sm font-semibold">
          Automatic checks{" "}
          <span className={failing ? "text-[#A32A12]" : "text-[#1E6B3A]"}>
            {failing ? `· ${failing} to fix` : "· all passed"}
          </span>
          {dirty && <span className="font-normal text-[#7A4A05]"> · rerun when you save</span>}
        </h3>
        <CheckList checks={current.checks} />
      </div>
      {error && (
        <p role="alert" className="text-sm text-[#A32A12]">
          {error}
        </p>
      )}
      {current.send_error && (
        <p className="text-sm text-[#A32A12]">Sending failed: {current.send_error}</p>
      )}
      {open ? (
        rejecting ? (
          <div className="flex flex-col gap-2">
            <label htmlFor="ap-reason" className="text-xs font-semibold text-[#3A4057]">
              Why reject it? (kept on the timeline)
            </label>
            <input
              id="ap-reason"
              className={field}
              value={reason}
              maxLength={300}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="flex gap-2">
              <button
                type="button"
                className={buttonDanger}
                disabled={busy || reason.trim().length < 3}
                onClick={() => run(() => api.rejectDraft(current.id, reason.trim()), "Rejected.")}
              >
                Reject draft
              </button>
              <button type="button" className={buttonSecondary} onClick={() => setRejecting(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={buttonPrimary}
              disabled={busy || (!dirty && failing > 0)}
              onClick={approve}
            >
              {busy ? "Working…" : "Approve and send"}
            </button>
            <button
              type="button"
              className={buttonSecondary}
              disabled={busy || !dirty}
              onClick={() => run(() => api.editDraft(current.id, subject, body))}
            >
              Save edits
            </button>
            <button type="button" className={buttonSecondary} onClick={() => setRejecting(true)}>
              Reject with reason
            </button>
          </div>
        )
      ) : (
        <p className="text-sm text-[#5A6075]">
          {current.status === "sent"
            ? `Sent ${current.sent_at ? new Date(current.sent_at).toLocaleString() : ""}.`
            : current.status === "rejected"
              ? `Rejected: ${current.rejection_reason}`
              : `Status: ${current.status.replace("_", " ")}.`}
        </p>
      )}
      <p className="text-xs text-[#5A6075]">
        {open && "Ctrl+Enter approves. "}
        Written by{" "}
        {current.source === "gemini"
          ? `Gemini (${current.model})`
          : current.source === "template"
            ? "a template"
            : "the offline AI"}
        {current.edited ? ", edited by your team" : ""}.
      </p>
    </section>
  );
}

export default function ApprovalsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("pending_approval");
  const [drafts, setDrafts] = useState<SavedDraft[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.drafts(tab);
      setDrafts(d);
      setSelected((s) => (s && d.some((x) => x.id === s) ? s : (d[0]?.id ?? null)));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [tab]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  const index = drafts?.findIndex((d) => d.id === selected) ?? -1;
  const current = index >= 0 && drafts ? drafts[index] : null;

  function move(step: number) {
    if (!drafts?.length) return;
    const next = drafts[Math.min(drafts.length - 1, Math.max(0, index + step))];
    setSelected(next.id);
    listRef.current?.querySelector<HTMLButtonElement>(`[data-id="${next.id}"]`)?.focus();
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">Approvals</h1>
          <p className="text-[#5A6075]">
            Nothing is sent until someone here approves it. Highest score first.
          </p>
        </div>
        <nav aria-label="Draft status" className="flex gap-1">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
              className={`rounded-lg px-3 py-2 text-sm font-semibold ${tab === key ? "bg-[#EEF0FF] text-[#3730A3]" : "text-[#3A4057] hover:bg-[#F6F7FB]"}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
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
      {error && (
        <p role="alert" className="text-[#A32A12]">
          {error}
        </p>
      )}
      {!drafts && !error && (
        <div aria-busy="true" className="h-64 animate-pulse rounded-xl bg-[#E9ECF4]" />
      )}
      {drafts && drafts.length === 0 && (
        <div className={`${card} p-8 text-center`}>
          <p className="font-semibold">
            {tab === "pending_approval" ? "Nothing waiting for approval" : "Nothing here yet"}
          </p>
          <p className="mt-1 text-sm text-[#5A6075]">
            New leads get a reply draft automatically; you can also write one from a lead&apos;s
            page.
          </p>
        </div>
      )}
      {drafts && drafts.length > 0 && (
        <div className="flex flex-wrap items-start gap-5">
          <ul
            ref={listRef}
            aria-label="Drafts"
            className={`${card} flex min-w-0 flex-[1_1_240px] flex-col overflow-hidden`}
            onKeyDown={(e) => {
              if (e.key === "j" || e.key === "ArrowDown") {
                e.preventDefault();
                move(1);
              } else if (e.key === "k" || e.key === "ArrowUp") {
                e.preventDefault();
                move(-1);
              }
            }}
          >
            {drafts.map((d) => (
              <li key={d.id} className="border-b border-[#EEF0F6] last:border-b-0">
                <button
                  type="button"
                  data-id={d.id}
                  aria-current={d.id === selected}
                  onClick={() => setSelected(d.id)}
                  className={`flex w-full flex-col gap-1 px-4 py-3 text-left ${d.id === selected ? "bg-[#EEF0FF]" : "hover:bg-[#F6F7FB]"}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{d.lead_name}</span>
                    {d.lead_score !== null && (
                      <span className="text-sm tabular-nums text-[#3A4057]">{d.lead_score}</span>
                    )}
                  </span>
                  <span className="truncate text-sm text-[#5A6075]">{d.subject}</span>
                  <span className="text-xs text-[#5A6075]">
                    {KIND_LABEL[d.kind] ?? "Reply"}
                    {d.all_passed ? "" : " · checks to fix"}
                  </span>
                </button>
              </li>
            ))}
            <li className="px-4 py-2 text-xs text-[#5A6075]">
              J / K or arrows move through the list.
            </li>
          </ul>
          {current && (
            <>
              <div className="flex min-w-0 flex-[1.3_1_300px] flex-col">
                <Context key={current.lead_id} draft={current} />
              </div>
              <div className="flex min-w-0 flex-[2_1_380px] flex-col">
                <Editor
                  key={current.id}
                  draft={current}
                  onDone={(msg) => {
                    setToast(msg);
                    load();
                  }}
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
