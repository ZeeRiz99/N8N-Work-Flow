"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PriorityBadge } from "@/components/badges";
import { card, timeAgo } from "@/components/ui-tokens";
import { api, errorText, type OverviewData, type TrendPoint } from "@/lib/api";

const BAR = "#4338CA"; // validated: lightness band, chroma, 3:1 vs surface (dataviz validator)
const RANGES = [7, 30, 90] as const;

function minutes(m: number | null): string {
  if (m === null) return "—";
  if (m < 60) return `${Math.round(m)} min`;
  const h = m / 60;
  return h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} days`;
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={`${card} flex flex-col gap-1 p-5`}>
      <span className="text-sm text-[#5A6075]">{label}</span>
      <span className="text-3xl font-bold tabular-nums">{value}</span>
      {note && <span className="text-xs text-[#5A6075]">{note}</span>}
    </div>
  );
}

/** Single-series bar chart: one hue, no legend (the title names the series), hover tooltip,
 *  2px gaps, rounded data-ends on the baseline, and a table view for screen readers. */
function LeadsPerDay({ series }: { series: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(1, ...series.map((p) => p.leads));
  const w = 720;
  const h = 180;
  const gap = 2;
  const bw = Math.max(2, w / series.length - gap);
  const fmt = (d: string) =>
    new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const ticks = [0, Math.round(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
  return (
    <section aria-labelledby="lpd-h" className={`${card} flex flex-col gap-3 p-5`}>
      <div className="flex items-center justify-between gap-2">
        <h2 id="lpd-h" className="font-semibold">
          New leads per day
        </h2>
        <button
          type="button"
          className="text-sm font-semibold text-[#4338CA] underline"
          onClick={() => setAsTable((v) => !v)}
        >
          {asTable ? "Show chart" : "Show as table"}
        </button>
      </div>
      {asTable ? (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-[#5A6075]">
                <th className="py-1 font-semibold">Day</th>
                <th className="py-1 text-right font-semibold">New leads</th>
                <th className="py-1 text-right font-semibold">High priority</th>
              </tr>
            </thead>
            <tbody>
              {series.map((p) => (
                <tr key={p.date} className="border-t border-[#EEF0F6]">
                  <td className="py-1">{fmt(p.date)}</td>
                  <td className="py-1 text-right tabular-nums">{p.leads}</td>
                  <td className="py-1 text-right tabular-nums">{p.high}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg
            viewBox={`0 -12 ${w + 40} ${h + 36}`}
            className="w-full"
            role="img"
            aria-label={`New leads per day, ${series.length} days, highest ${max}`}
            onMouseLeave={() => setHover(null)}
          >
            {ticks.map((t) => {
              const y = h - (t / max) * h;
              return (
                <g key={t}>
                  <line x1={32} x2={w + 32} y1={y} y2={y} stroke="#EEF0F6" strokeWidth={1} />
                  <text x={26} y={y + 4} textAnchor="end" fontSize="11" fill="#5A6075">
                    {t}
                  </text>
                </g>
              );
            })}
            {series.map((p, i) => {
              const bh = (p.leads / max) * h;
              const x = 32 + i * (bw + gap);
              return (
                <g key={p.date} onMouseEnter={() => setHover(i)}>
                  {/* hit target taller than the mark */}
                  <rect x={x} y={0} width={bw + gap} height={h} fill="transparent" />
                  {p.leads > 0 && (
                    <path
                      d={`M${x},${h} v${-Math.max(bh - 4, 0)} q0,-4 4,-4 h${Math.max(bw - 8, 0)} q4,0 4,4 v${Math.max(bh - 4, 0)} z`}
                      fill={BAR}
                      opacity={hover === null || hover === i ? 1 : 0.55}
                    />
                  )}
                </g>
              );
            })}
            {[0, Math.floor(series.length / 2), series.length - 1].map((i) => (
              <text
                key={i}
                x={
                  i === series.length - 1
                    ? 32 + series.length * (bw + gap) - gap
                    : i === 0
                      ? 32
                      : 32 + i * (bw + gap) + bw / 2
                }
                y={h + 18}
                textAnchor={i === 0 ? "start" : i === series.length - 1 ? "end" : "middle"}
                fontSize="11"
                fill="#5A6075"
              >
                {series[i] ? fmt(series[i].date) : ""}
              </text>
            ))}
          </svg>
          {hover !== null && series[hover] && (
            <div
              role="status"
              className="pointer-events-none absolute top-0 rounded-md bg-[#1A1D2B] px-2.5 py-1.5 text-xs text-white"
              style={{ left: `${Math.min(80, ((hover + 0.5) / series.length) * 100)}%` }}
            >
              <div className="font-semibold">{fmt(series[hover].date)}</div>
              <div>
                {series[hover].leads} new · {series[hover].high} high priority
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ShareBars({
  title,
  rows,
}: {
  title: string;
  rows: { key: string; label: React.ReactNode; count: number; share: number }[];
}) {
  return (
    <section className={`${card} flex flex-col gap-3 p-5`}>
      <h2 className="font-semibold">{title}</h2>
      <ul className="flex flex-col gap-2.5">
        {rows.map((r) => (
          <li key={r.key} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span>{r.label}</span>
              <span className="tabular-nums text-[#3A4057]">
                {r.count} · {Math.round(r.share * 100)}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#EEF0F6]" aria-hidden="true">
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.max(r.share * 100, r.count ? 2 : 0)}%`, background: BAR }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function OverviewPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);
  const [data, setData] = useState<OverviewData | null>(null);
  const [series, setSeries] = useState<TrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([api.overview(days), api.trends(Math.max(days, 14))])
      .then(([o, t]) => {
        if (!live) return;
        setData(o);
        setSeries(t.series);
        setError(null);
      })
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [days]);

  if (error && !data) {
    return (
      <p role="alert" className="text-[#A32A12]">
        {error}
      </p>
    );
  }
  if (!data) return <div aria-busy="true" className="h-64 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  const c = data.cards;
  const delta = c.new_leads - c.new_leads_previous;
  const stagesTotal = data.stages.reduce((a, s) => a + s.count, 0) || 1;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">Overview</h1>
          <p className="text-[#5A6075]">How your leads are doing, last {days} days.</p>
        </div>
        <div role="group" aria-label="Time range" className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={days === r}
              onClick={() => setDays(r)}
              className={`rounded-lg px-3 py-2 text-sm font-semibold ${days === r ? "bg-[#EEF0FF] text-[#3730A3]" : "text-[#3A4057] hover:bg-[#F6F7FB]"}`}
            >
              {r} days
            </button>
          ))}
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="New leads"
          value={String(c.new_leads)}
          note={`${delta >= 0 ? "+" : ""}${delta} vs the previous ${days} days`}
        />
        <Stat label="High priority" value={String(c.high_priority)} note="Reply to these first" />
        <Stat
          label="Waiting for approval"
          value={String(c.awaiting_approval)}
          note="Reply drafts in Approvals"
        />
        <Stat
          label="Median time to first reply"
          value={minutes(c.median_first_reply_minutes)}
          note={`Target ${minutes(c.reply_target_minutes)} · ${c.answered_leads} answered`}
        />
      </div>

      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-[2_1_480px]">
          <LeadsPerDay series={series} />
        </div>
        <div className="min-w-0 flex-[1_1_280px]">
          <ShareBars
            title="Priority mix (share of new leads)"
            rows={data.priority_mix
              .filter((m) => m.priority !== "unscored" || m.count > 0)
              .map((m) => ({
                key: m.priority,
                label: <PriorityBadge priority={m.priority} />,
                count: m.count,
                share: m.share,
              }))}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-[1_1_300px]">
          <ShareBars
            title="Pipeline now"
            rows={data.stages.map((s) => ({
              key: s.label,
              label: s.label,
              count: s.count,
              share: s.count / stagesTotal,
            }))}
          />
        </div>
        <section className={`${card} min-w-0 flex-[2_1_480px] overflow-hidden`}>
          <div className="flex items-center justify-between gap-2 px-5 pt-5 pb-3">
            <h2 className="font-semibold">Latest leads</h2>
            <Link href="/leads" className="text-sm font-semibold text-[#4338CA]">
              All leads →
            </Link>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs text-[#5A6075]">
                <th className="px-5 py-2 font-semibold">Lead</th>
                <th className="px-3 py-2 font-semibold">Priority</th>
                <th className="px-3 py-2 font-semibold">Next step</th>
                <th className="px-3 py-2 font-semibold">Activity</th>
              </tr>
            </thead>
            <tbody>
              {data.latest.map((l) => (
                <tr key={l.id} className="border-b border-[#EEF0F6] last:border-b-0">
                  <td className="px-5 py-2.5">
                    <Link href={`/leads/${l.id}`} className="font-semibold no-underline">
                      {l.full_name}
                    </Link>
                    <div className="text-xs text-[#5A6075]">{l.company ?? "No company given"}</div>
                  </td>
                  <td className="px-3 py-2.5">
                    <PriorityBadge priority={l.priority} />
                  </td>
                  <td className="px-3 py-2.5">{l.next_step}</td>
                  <td className="px-3 py-2.5 text-[#5A6075]">{timeAgo(l.last_interaction_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className={`${card} flex flex-wrap items-center gap-6 p-5 text-sm`}>
        <h2 className="font-semibold">Automation this week</h2>
        <span>
          <strong className="tabular-nums">{data.automation_week.runs}</strong> workflow runs
        </span>
        <span>
          <strong className="tabular-nums">{data.automation_week.alerts}</strong> team alerts
        </span>
        <span>
          <strong className="tabular-nums">{data.automation_week.emails_sent}</strong> approved
          emails sent
        </span>
        <Link href="/automation" className="ml-auto font-semibold text-[#4338CA]">
          Automation Center →
        </Link>
      </section>
    </div>
  );
}
