"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonSecondary, card } from "@/components/ui-tokens";
import {
  api,
  errorText,
  type FunnelData,
  type ReportSnapshot,
  type SourceRow,
  type TeamRow,
} from "@/lib/api";

const BAR = "#4338CA"; // single validated hue; values are always shown as text too
const RANGES = [30, 90, 365] as const;
const TABS = [
  ["sources", "Sources"],
  ["funnel", "Funnel"],
  ["team", "Team"],
  ["reports", "Reports"],
] as const;
const pct = (x: number) => `${Math.round(x * 100)}%`;

function Bar({ value, max }: { value: number; max: number }) {
  return (
    <div className="h-2 min-w-[80px] overflow-hidden rounded-full bg-[#EEF0F6]" aria-hidden="true">
      <div
        className="h-full rounded-full"
        style={{
          width: `${max ? Math.max((value / max) * 100, value ? 2 : 0) : 0}%`,
          background: BAR,
        }}
      />
    </div>
  );
}

function Sources({ days }: { days: number }) {
  const [rows, setRows] = useState<SourceRow[] | null>(null);
  useEffect(() => {
    api
      .analyticsSources(days)
      .then((r) => setRows(r.rows))
      .catch(() => setRows([]));
  }, [days]);
  if (!rows) return <div aria-busy="true" className="h-40 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  const max = Math.max(1, ...rows.map((r) => r.leads));
  return (
    <section className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[640px] text-sm">
        <caption className="px-5 pt-5 pb-3 text-left font-semibold">
          Lead sources, last {days} days
        </caption>
        <thead>
          <tr className="border-y border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs text-[#5A6075]">
            <th className="px-5 py-2 font-semibold">Source</th>
            <th className="px-3 py-2 font-semibold">Leads</th>
            <th className="px-3 py-2 text-right font-semibold">High</th>
            <th className="px-3 py-2 text-right font-semibold">Won</th>
            <th className="px-3 py-2 text-right font-semibold">Conversion</th>
            <th className="px-3 py-2 text-right font-semibold">Median score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source} className="border-b border-[#EEF0F6] last:border-b-0">
              <td className="px-5 py-2.5 font-medium">{r.source}</td>
              <td className="px-3 py-2.5">
                <div className="flex items-center gap-3">
                  <span className="w-8 tabular-nums">{r.leads}</span>
                  <Bar value={r.leads} max={max} />
                </div>
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.high}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.won}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{pct(r.conversion)}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.median_score ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Funnel({ days }: { days: number }) {
  const [f, setF] = useState<FunnelData | null>(null);
  useEffect(() => {
    api
      .analyticsFunnel(days)
      .then(setF)
      .catch(() => undefined);
  }, [days]);
  if (!f) return <div aria-busy="true" className="h-40 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  const max = Math.max(1, f.total);
  return (
    <section className={`${card} flex flex-col gap-4 p-5`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Funnel, leads from the last {days} days</h2>
        <span className="text-sm text-[#3A4057]">
          {f.total} leads · {pct(f.win_rate)} won · {f.lost} lost
        </span>
      </div>
      <ol className="flex flex-col gap-3">
        {f.steps.map((s) => (
          <li key={s.key} className="grid grid-cols-[150px_1fr_auto] items-center gap-3 text-sm">
            <span className="font-medium">{s.label}</span>
            <Bar value={s.reached} max={max} />
            <span className="tabular-nums text-[#3A4057]">
              {s.reached} · {pct(s.from_previous)} of previous
            </span>
          </li>
        ))}
      </ol>
      <p className="text-xs text-[#5A6075]">
        A lead counts at its current stage and every stage before it; won leads passed them all.
      </p>
    </section>
  );
}

function Team({ days }: { days: number }) {
  const [rows, setRows] = useState<TeamRow[] | null>(null);
  useEffect(() => {
    api
      .analyticsTeam(days)
      .then((r) => setRows(r.rows))
      .catch(() => setRows([]));
  }, [days]);
  if (!rows) return <div aria-busy="true" className="h-40 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  return (
    <section className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[560px] text-sm">
        <caption className="px-5 pt-5 pb-3 text-left font-semibold">Team, last {days} days</caption>
        <thead>
          <tr className="border-y border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs text-[#5A6075]">
            <th className="px-5 py-2 font-semibold">Member</th>
            <th className="px-3 py-2 text-right font-semibold">Assigned leads</th>
            <th className="px-3 py-2 text-right font-semibold">Drafts approved</th>
            <th className="px-3 py-2 text-right font-semibold">Emails sent</th>
            <th className="px-3 py-2 text-right font-semibold">Won</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.user_id} className="border-b border-[#EEF0F6] last:border-b-0">
              <td className="px-5 py-2.5">
                <span className="font-medium">{r.name}</span>{" "}
                <span className="text-xs text-[#5A6075]">{r.role}</span>
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.assigned}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.approved}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.sent}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{r.won}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Reports() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [items, setItems] = useState<ReportSnapshot[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = () =>
    api
      .reports()
      .then(setItems)
      .catch((e) => setMessage(errorText(e)));
  useEffect(() => {
    load();
  }, []);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[70ch] text-sm text-[#5A6075]">
          Saved summaries. Every number comes from the database; if AI-written text contains a
          number that is not in the data, a plain template is used instead.
        </p>
        {isAdmin && (
          <div className="flex gap-2">
            {(
              [
                ["daily", "Daily summary now"],
                ["source_performance", "Source report now"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={buttonSecondary}
                onClick={async () => {
                  try {
                    await api.makeReport(k);
                    setMessage("Report saved.");
                    load();
                  } catch (e) {
                    setMessage(errorText(e));
                  }
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}
      {items?.length === 0 && (
        <div className={`${card} p-8 text-center text-sm text-[#5A6075]`}>
          No reports yet. The daily summary is made each morning at 08:30 local time.
        </div>
      )}
      <ul className="flex flex-col gap-3">
        {items?.map((r) => (
          <li key={r.id} className={`${card} flex flex-col gap-2 p-5`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-semibold">
                {r.kind === "daily" ? "Daily summary" : "Lead sources, 7 days"} ·{" "}
                {new Date(r.period_start).toLocaleDateString(undefined, { dateStyle: "medium" })}
              </h3>
              <span className="text-xs text-[#5A6075]">
                {r.narrative_source === "ai" ? "Written by AI, numbers checked" : "Template"}
              </span>
            </div>
            <p className="max-w-[75ch] text-sm leading-relaxed">{r.narrative}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AnalyticsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("sources");
  const [days, setDays] = useState<(typeof RANGES)[number]>(90);
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">Analytics</h1>
          <p className="text-[#5A6075]">
            Where leads come from, how far they get, and who works them.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {tab !== "reports" &&
            RANGES.map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={days === r}
                onClick={() => setDays(r)}
                className={`rounded-lg px-3 py-2 text-sm font-semibold ${days === r ? "bg-[#EEF0FF] text-[#3730A3]" : "text-[#3A4057] hover:bg-[#F6F7FB]"}`}
              >
                {r === 365 ? "1 year" : `${r} days`}
              </button>
            ))}
          <a href={api.analyticsExportUrl(days)} className={buttonSecondary} download>
            Export CSV
          </a>
        </div>
      </header>
      <nav aria-label="Analytics sections" className="flex gap-2 border-b border-[#E3E6EF]">
        {TABS.map(([k, label]) => (
          <button
            key={k}
            type="button"
            aria-current={tab === k ? "page" : undefined}
            onClick={() => setTab(k)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${tab === k ? "border-[#4338CA] text-[#3730A3]" : "border-transparent text-[#5A6075] hover:text-[#1A1D2B]"}`}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "sources" && <Sources days={days} />}
      {tab === "funnel" && <Funnel days={days} />}
      {tab === "team" && <Team days={days} />}
      {tab === "reports" && <Reports />}
    </div>
  );
}
