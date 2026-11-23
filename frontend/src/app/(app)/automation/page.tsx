"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonSecondary, card, timeAgo } from "@/components/ui-tokens";
import { api, errorText, type AutomationOverview } from "@/lib/api";

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  success: { label: "Success", color: "#1E6B3A", bg: "#E3F4E9" },
  skipped: { label: "Skipped (already handled)", color: "#444B63", bg: "#E8EBF3" },
  failed: { label: "Failed", color: "#A32A12", bg: "#FCE7E1" },
  running: { label: "Running", color: "#1F4E79", bg: "#E6F0FA" },
  retrying: { label: "Retrying", color: "#7A4A05", bg: "#FDF0C8" },
};

function StatusPill({ status }: { status: string | null }) {
  if (!status) return <span className="text-sm text-[#5A6075]">No runs yet</span>;
  const s = STATUS[status] ?? STATUS.running;
  return (
    <span
      className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={{ color: s.color, background: s.bg }}
    >
      {s.label}
    </span>
  );
}

export default function AutomationPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [data, setData] = useState<AutomationOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.automation());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    const timer = setInterval(load, 15000);
    return () => {
      clearTimeout(t);
      clearInterval(timer);
    };
  }, [load]);

  if (error && !data) {
    return (
      <p role="alert" className="text-[#A32A12]">
        {error}
      </p>
    );
  }
  if (!data) return <div aria-busy="true" className="h-64 animate-pulse rounded-xl bg-[#E9ECF4]" />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">Automation</h1>
          <p className="text-[#5A6075]">
            n8n moves each lead along; Replyline decides. Nothing is sent without approval.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2 text-sm">
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: data.n8n.ok ? "#1E6B3A" : "#A32A12" }}
            />
            n8n {data.n8n.ok ? "connected" : `not reachable (${data.n8n.detail})`}
          </span>
          <a
            href={data.n8n.editor_url}
            target="_blank"
            rel="noreferrer"
            className={buttonSecondary}
          >
            Open n8n editor
          </a>
        </div>
      </header>

      <section aria-labelledby="journey-h" className={`${card} flex flex-col gap-3 p-6`}>
        <h2 id="journey-h" className="text-base font-semibold">
          The lead journey, last 7 days
        </h2>
        <ol className="flex flex-wrap items-stretch gap-2">
          {data.journey.map((step, i) => (
            <li key={step.key} className="flex items-center gap-2">
              <div
                className={`flex min-w-[118px] flex-col rounded-lg border px-3 py-2 ${step.key === "you" ? "border-[#4338CA] bg-[#EEF0FF]" : "border-[#E3E6EF]"}`}
              >
                <span className="text-xs text-[#5A6075]">
                  {step.key === "you" ? "You" : step.key}
                </span>
                <span className="text-xl font-bold tabular-nums">{step.count}</span>
                <span className="text-xs text-[#3A4057]">{step.label}</span>
              </div>
              {i < data.journey.length - 1 && (
                <span aria-hidden="true" className="text-[#7B8299]">
                  →
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        {data.workflows.map((w) => (
          <section key={w.key} className={`${card} flex flex-col gap-2 p-5`}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-semibold">
                {w.key} · {w.name}
              </h2>
            </div>
            <p className="text-sm text-[#5A6075]">{w.purpose}</p>
            <dl className="mt-1 grid grid-cols-3 gap-2 text-center text-sm">
              <div>
                <dt className="text-xs text-[#5A6075]">Runs</dt>
                <dd className="font-semibold tabular-nums">{w.runs_7d}</dd>
              </div>
              <div>
                <dt className="text-xs text-[#5A6075]">Skipped</dt>
                <dd className="font-semibold tabular-nums">{w.skipped_7d}</dd>
              </div>
              <div>
                <dt className="text-xs text-[#5A6075]">Failed</dt>
                <dd
                  className="font-semibold tabular-nums"
                  style={{ color: w.failed_7d ? "#A32A12" : undefined }}
                >
                  {w.failed_7d}
                </dd>
              </div>
            </dl>
            <div className="flex items-center justify-between gap-2 text-xs text-[#5A6075]">
              <StatusPill status={w.last_status} />
              {w.last_run_at && <span>{timeAgo(w.last_run_at)}</span>}
            </div>
          </section>
        ))}
      </div>

      <section className={`${card} flex flex-wrap items-center justify-between gap-3 p-5`}>
        <div>
          <h2 className="font-semibold">Deliveries to n8n</h2>
          <p className="text-sm text-[#5A6075]">
            {data.outbox.pending} waiting · {data.outbox.failed} gave up. Every event is kept, so
            nothing is lost while n8n is down.
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            className={buttonSecondary}
            disabled={data.outbox.failed === 0}
            onClick={async () => {
              try {
                const r = await api.redispatch();
                setMessage(`Retrying ${r.requeued} deliveries.`);
                load();
              } catch (e) {
                setMessage(errorText(e));
              }
            }}
          >
            Retry failed deliveries
          </button>
        )}
        {message && (
          <p role="status" className="w-full text-sm text-[#3A4057]">
            {message}
          </p>
        )}
      </section>

      <section aria-labelledby="runs-h" className={`${card} overflow-hidden`}>
        <h2 id="runs-h" className="px-5 pt-5 pb-3 text-base font-semibold">
          Recent runs
        </h2>
        {data.recent.length === 0 ? (
          <p className="px-5 pb-5 text-sm text-[#5A6075]">No runs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-y border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs text-[#5A6075]">
                  <th className="px-5 py-2 font-semibold">Workflow</th>
                  <th className="px-3 py-2 font-semibold">Result</th>
                  <th className="px-3 py-2 font-semibold">What happened</th>
                  <th className="px-3 py-2 font-semibold">Request ID</th>
                  <th className="px-3 py-2 font-semibold">When</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((r) => (
                  <tr
                    key={`${r.workflow_key}-${r.n8n_execution_id}`}
                    className="border-b border-[#EEF0F6]"
                  >
                    <td className="px-5 py-2.5 font-semibold">{r.workflow_key}</td>
                    <td className="px-3 py-2.5">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="max-w-[340px] px-3 py-2.5 text-[#3A4057]">
                      {r.error
                        ? `${String(r.meta.last_node ?? "A step")} failed: ${r.error}`
                        : r.meta.duplicate_delivery || r.status === "skipped"
                          ? "Same event delivered again; handled once, nothing repeated."
                          : r.meta.result === "sent"
                            ? "Approved email sent."
                            : r.meta.result === "failed"
                              ? "Email could not be sent (mail server refused). Marked failed; it is not retried by itself."
                              : r.meta.band
                                ? `Scored ${String(r.meta.score)}, ${String(r.meta.band)}${r.meta.draft_id ? "; draft written" : ""}`
                                : "Done."}
                      {r.lead_id && (
                        <>
                          {" "}
                          <Link href={`/leads/${r.lead_id}`} className="text-[#4338CA]">
                            Lead
                          </Link>
                        </>
                      )}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-[#5A6075]">
                      {r.request_id ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-[#5A6075]">{timeAgo(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
