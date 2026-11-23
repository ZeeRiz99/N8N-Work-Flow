"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PriorityBadge } from "@/components/badges";
import { buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, errorText, type FollowUpItem } from "@/lib/api";

const TABS = [
  ["scheduled", "Scheduled"],
  ["awaiting_approval", "Draft waiting"],
  ["done", "Done"],
  ["skipped", "Skipped"],
] as const;

function when(iso: string): string {
  const d = new Date(iso);
  const days = Math.round((d.getTime() - Date.now()) / 86_400_000);
  const date = d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  if (days === 0) return `Today · ${date}`;
  return days > 0
    ? `In ${days} day${days === 1 ? "" : "s"} · ${date}`
    : `${-days} day${days === -1 ? "" : "s"} overdue · ${date}`;
}

export default function FollowUpsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("scheduled");
  const [items, setItems] = useState<FollowUpItem[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [skipping, setSkipping] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.followUps(tab));
    } catch (e) {
      setMessage(errorText(e));
    }
  }, [tab]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(id: string, fn: () => Promise<{ status?: string; reason?: string }>) {
    setBusy(id);
    setMessage(null);
    try {
      const r = await fn();
      setMessage(
        r.status === "awaiting_approval"
          ? "Draft written. Review it in Approvals; nothing is sent until you approve."
          : r.status === "skipped"
            ? `Skipped: ${r.reason ?? "the contact rules are not met"}.`
            : "Done.",
      );
      setSkipping(null);
      setReason("");
      await load();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">Follow-ups</h1>
          <p className="max-w-[70ch] text-[#5A6075]">
            After each email, Replyline schedules the next follow-up. When it falls due (in your
            business hours), the contact rules are checked; if they pass, a draft goes to Approvals.
            Replies, opt-outs and the attempt limit stop it automatically.
          </p>
        </div>
        <nav aria-label="Follow-up status" className="flex flex-wrap gap-1">
          {TABS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={tab === k}
              onClick={() => setTab(k)}
              className={`rounded-lg px-3 py-2 text-sm font-semibold ${tab === k ? "bg-[#EEF0FF] text-[#3730A3]" : "text-[#3A4057] hover:bg-[#F6F7FB]"}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      {message && (
        <p role="status" className="rounded-lg bg-[#1A1D2B] px-4 py-2.5 text-sm text-white">
          {message}
        </p>
      )}
      {!items && <div aria-busy="true" className="h-48 animate-pulse rounded-xl bg-[#E9ECF4]" />}
      {items && items.length === 0 && (
        <div className={`${card} p-8 text-center`}>
          <p className="font-semibold">Nothing here</p>
          <p className="mt-1 text-sm text-[#5A6075]">
            Follow-ups appear after a reply has been sent, or when you schedule one on a lead.
          </p>
        </div>
      )}
      {items && items.length > 0 && (
        <ul className={`${card} flex flex-col overflow-hidden`}>
          {items.map((f) => (
            <li
              key={f.id}
              className="flex flex-col gap-2 border-b border-[#EEF0F6] p-4 last:border-b-0"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/leads/${f.lead_id}`} className="font-semibold no-underline">
                      {f.lead_name}
                    </Link>
                    {f.lead_priority && <PriorityBadge priority={f.lead_priority} />}
                    <span className="text-xs text-[#5A6075]">Attempt {f.attempt_no}</span>
                  </div>
                  <p className="text-sm text-[#5A6075]">
                    {f.lead_company ?? "No company given"} · {when(f.due_at)}
                  </p>
                  {f.skip_reason && <p className="text-sm text-[#7A4A05]">Why: {f.skip_reason}</p>}
                </div>
                <div className="flex flex-wrap gap-2">
                  {f.status === "scheduled" && (
                    <>
                      <button
                        type="button"
                        className={buttonSecondary}
                        disabled={busy === f.id}
                        onClick={() => run(f.id, () => api.prepareFollowUp(f.id))}
                      >
                        {busy === f.id ? "Checking…" : "Prepare now"}
                      </button>
                      <button
                        type="button"
                        className={buttonSecondary}
                        onClick={() => setSkipping(skipping === f.id ? null : f.id)}
                      >
                        Skip
                      </button>
                    </>
                  )}
                  {f.status === "awaiting_approval" && (
                    <Link href="/approvals" className={buttonSecondary}>
                      Review draft
                    </Link>
                  )}
                </div>
              </div>
              {skipping === f.id && (
                <div className="flex flex-wrap items-end gap-2">
                  <div className="flex min-w-[240px] flex-1 flex-col gap-1">
                    <label
                      htmlFor={`skip-${f.id}`}
                      className="text-xs font-semibold text-[#3A4057]"
                    >
                      Why skip it?
                    </label>
                    <input
                      id={`skip-${f.id}`}
                      className={field}
                      value={reason}
                      maxLength={200}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>
                  <button
                    type="button"
                    className={buttonSecondary}
                    disabled={reason.trim().length < 3}
                    onClick={() => run(f.id, () => api.skipFollowUp(f.id, reason.trim()))}
                  >
                    Skip follow-up
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
