"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AiStatusPill, PriorityBadge } from "@/components/badges";
import { api, ApiError, AuthRequired, type LeadRow, type Page } from "@/lib/api";

const POLL_FAST_MS = 2000; // while any lead is still being analyzed
const POLL_SLOW_MS = 10000;

function timeAgo(iso: string): string {
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 45) return "Just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export function LeadsTable() {
  const [data, setData] = useState<Page<LeadRow> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.leads());
      setError(null);
    } catch (e) {
      if (e instanceof AuthRequired) {
        window.location.assign("/login?next=/leads");
        return;
      }
      const rid = e instanceof ApiError ? e.body?.error.request_id : undefined;
      setError(
        e instanceof ApiError
          ? `${e.message}${rid ? ` (request ${rid})` : ""}`
          : "The backend is not reachable. Is it running on port 8000?",
      );
    }
  }, []);

  const busy = data?.items.some((l) => l.ai_status === "pending" || l.ai_status === "processing");

  useEffect(() => {
    const first = setTimeout(load, 0);
    const timer = setInterval(load, busy ? POLL_FAST_MS : POLL_SLOW_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [load, busy]);

  if (error && !data) {
    return (
      <div role="alert" className="rounded-xl border border-[#F2C2B5] bg-[#FEF6F3] p-5">
        <p className="font-semibold text-[#A32A12]">Could not load leads</p>
        <p className="mt-1 text-sm text-[#3A4057]">{error}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 min-h-11 rounded-lg border border-[#CDD2E0] bg-white px-4 font-medium"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div aria-busy="true" className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-[#E9ECF4]" />
        ))}
      </div>
    );
  }

  if (data.items.length === 0) {
    return (
      <div className="rounded-xl border border-[#E3E6EF] bg-white p-8 text-center">
        <p className="font-semibold">No leads yet</p>
        <p className="mt-1 text-sm text-[#5A6075]">
          Submit the public form and the lead appears here within a few seconds.
        </p>
        <Link
          href="/f/harbor-web"
          className="mt-4 inline-flex min-h-11 items-center rounded-lg bg-[#4338CA] px-4 font-semibold text-white"
        >
          Open the public form
        </Link>
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-xl border border-[#E3E6EF] bg-white">
      <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
        <p className="text-sm text-[#5A6075]">
          {data.total} {data.total === 1 ? "lead" : "leads"}
          {busy ? " · updating while AI works" : ""}
        </p>
        {error && <p className="text-xs text-[#A32A12]">Last refresh failed; retrying.</p>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="border-y border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs font-semibold text-[#5A6075]">
              <th scope="col" className="px-4 py-2.5">
                Lead
              </th>
              <th scope="col" className="px-4 py-2.5">
                Latest message
              </th>
              <th scope="col" className="px-4 py-2.5">
                Score
              </th>
              <th scope="col" className="px-4 py-2.5">
                Priority
              </th>
              <th scope="col" className="px-4 py-2.5">
                Received
              </th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((lead) => (
              <tr key={lead.id} className="border-b border-[#EEF0F6] align-top last:border-0">
                <td className="px-4 py-3">
                  <div className="font-semibold">{lead.full_name}</div>
                  <div className="text-xs text-[#5A6075]">{lead.company ?? "No company given"}</div>
                  {lead.inquiries > 1 && (
                    <div className="mt-1 text-xs text-[#3A4057]">{lead.inquiries} messages</div>
                  )}
                </td>
                <td className="max-w-[340px] px-4 py-3 text-[#3A4057]">{lead.latest_message}</td>
                <td className="px-4 py-3 tabular-nums">
                  {lead.score === null ? (
                    <span className="text-[#5A6075]">—</span>
                  ) : (
                    <>
                      <strong>{lead.score}</strong>
                      {lead.score_source === "fake" && (
                        <span className="ml-1.5 text-xs text-[#5A6075]">(fake AI)</span>
                      )}
                    </>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col items-start gap-1">
                    <PriorityBadge priority={lead.priority} />
                    <AiStatusPill status={lead.ai_status} />
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-[#5A6075]">
                  {timeAgo(lead.last_interaction_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
