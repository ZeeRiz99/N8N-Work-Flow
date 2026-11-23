"use client";

import { useState } from "react";

import { buttonSecondary, card, timeAgo } from "@/components/ui-tokens";
import { errorText, type Facts, type LeadAnalysis } from "@/lib/api";

const URGENCY: Record<string, string> = {
  immediate: "Immediately",
  soon: "Soon",
  flexible: "Flexible",
  unspecified: "Not stated",
};
const INTENT: Record<string, string> = {
  hiring: "Ready to hire",
  researching: "Researching",
  price_check: "Checking prices",
  support_request: "Support request",
  partnership: "Partnership",
  job_seeker: "Job seeker",
  spam: "Spam",
  unknown: "Unclear",
};

export function sourceLabel(source: string | null, provisional: boolean): string | null {
  if (provisional) return "provisional";
  if (source === "fake") return "offline AI";
  return null;
}

function money(minor: number | null, currency: string): string {
  if (minor === null) return "?";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.length === 3 ? currency : "USD",
    maximumFractionDigits: 0,
  }).format(minor / 100);
}

/** A grounded fact: the value, then the customer's own words it came from. */
function Fact({
  label,
  value,
  evidence,
  source,
}: {
  label: string;
  value: string;
  evidence?: string | null;
  source?: string | null;
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-[#EEF0F6] py-2.5 last:border-b-0">
      <dt className="text-xs font-semibold text-[#5A6075]">{label}</dt>
      <dd className="font-medium">{value}</dd>
      {evidence ? (
        <dd className="text-[13px] text-[#3A4057]">
          <span className="sr-only">Customer wrote: </span>
          <q className="rounded bg-[#FFF6D6] px-1 italic">{evidence}</q>
        </dd>
      ) : source === "form" ? (
        <dd className="text-[13px] text-[#5A6075]">Chosen on the form</dd>
      ) : null}
    </div>
  );
}

function FactList({ facts, intent }: { facts: Facts; intent: string | null }) {
  const b = facts.budget;
  const t = facts.timeline;
  const items: React.ReactNode[] = [];
  for (const s of facts.services) {
    items.push(
      <Fact
        key={`s-${s.name}`}
        label="Service"
        value={s.name ?? "Other"}
        evidence={s.evidence}
        source={s.source}
      />,
    );
  }
  if (b) {
    const range =
      b.min_minor !== null && b.max_minor !== null && b.min_minor !== b.max_minor
        ? `${money(b.min_minor, b.currency)} to ${money(b.max_minor, b.currency)}`
        : money(b.max_minor ?? b.min_minor, b.currency);
    items.push(
      <Fact
        key="budget"
        label="Budget"
        value={b.comparable ? range : `${range} (not compared: different currency)`}
        evidence={b.evidence}
        source={b.source}
      />,
    );
  }
  if (t.source) {
    items.push(
      <Fact
        key="timeline"
        label="Timeline"
        value={`${t.text ?? ""}${t.text ? " · " : ""}${URGENCY[t.urgency] ?? t.urgency}`}
        evidence={t.evidence}
        source={t.source}
      />,
    );
  }
  if (intent) {
    items.push(<Fact key="intent" label="Intent" value={INTENT[intent] ?? intent} />);
  }
  if (facts.industry) items.push(<Fact key="ind" label="Industry" value={facts.industry} />);
  for (const [i, r] of facts.requirements.entries()) {
    items.push(<Fact key={`r-${i}`} label="Needs" value={r.text ?? ""} evidence={r.evidence} />);
  }
  for (const [i, s] of facts.buying_signals.entries()) {
    items.push(
      <Fact key={`b-${i}`} label="Buying signal" value={s.text ?? ""} evidence={s.evidence} />,
    );
  }
  if (items.length === 0) {
    return <p className="text-sm text-[#5A6075]">No facts could be confirmed from the message.</p>;
  }
  return <dl className="flex flex-col">{items}</dl>;
}

export function AnalysisPanel({
  data,
  onReanalyze,
}: {
  data: LeadAnalysis;
  onReanalyze: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const a = data.analysis;
  const s = data.score;

  async function rerun() {
    setBusy(true);
    setError(null);
    try {
      await onReanalyze();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="ai-h" className={`${card} flex flex-col gap-4 p-6`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="ai-h" className="text-base font-semibold">
          AI analysis
        </h2>
        <button type="button" className={buttonSecondary} disabled={busy} onClick={rerun}>
          {busy ? "Analyzing…" : "Re-analyze"}
        </button>
      </div>
      {error && <p className="text-sm text-[#A32A12]">{error}</p>}

      {!a ? (
        <p className="text-sm text-[#5A6075]">Not analyzed yet.</p>
      ) : (
        <>
          {(s?.needs_review || a.guard_flags.length > 0) && (
            <div
              role="note"
              className="rounded-lg border border-[#F2C2B5] bg-[#FEF6F3] p-3 text-sm"
            >
              <p className="font-semibold text-[#A32A12]">Needs a human look</p>
              <p className="mt-0.5">
                {a.guard_flags.length > 0
                  ? "The message contains text that tries to instruct the AI. It was treated as data, and the AI's judgment was not used in the score."
                  : "Something about this lead (for example a throwaway email) means the score should be checked."}
              </p>
            </div>
          )}
          {a.status === "failed" && (
            <div
              role="note"
              className="rounded-lg border border-[#F5D7A8] bg-[#FFF8EC] p-3 text-sm"
            >
              <p className="font-semibold text-[#7A4A05]">AI was unavailable</p>
              <p className="mt-0.5">
                The score below is provisional, from the form choices and contact details only.
                Re-analyze to try again.
              </p>
            </div>
          )}
          {a.summary && <p className="max-w-[68ch] leading-relaxed">{a.summary}</p>}
          {a.recommended_next_action && (
            <p className="rounded-lg bg-[#EEF0FF] px-3 py-2 text-sm text-[#2D2A8C]">
              <span className="font-semibold">Suggested next step: </span>
              {a.recommended_next_action}
            </p>
          )}
          {a.status === "done" ? (
            <FactList facts={a.facts} intent={!s?.needs_review ? a.intent : null} />
          ) : (
            <p className="text-sm text-[#5A6075]">
              The AI did not read this message, so only form choices are shown.
            </p>
          )}
          {a.facts.missing_info.length > 0 && (
            <div className="text-sm">
              <span className="font-semibold">Still unknown: </span>
              {a.facts.missing_info.join(", ")}
            </div>
          )}
          {(a.facts.rejected.length > 0 || a.facts.conflicts.length > 0) && (
            <details className="text-sm text-[#3A4057]">
              <summary className="cursor-pointer font-semibold">
                {a.facts.rejected.length} unconfirmed claim
                {a.facts.rejected.length === 1 ? "" : "s"} removed
                {a.facts.conflicts.length > 0 ? `, ${a.facts.conflicts.length} conflict` : ""}
              </summary>
              <ul className="mt-1.5 list-disc pl-5">
                {a.facts.rejected.map((r, i) => (
                  <li key={`r${i}`}>
                    {r.field.replaceAll("_", " ")}: {r.reason}
                  </li>
                ))}
                {a.facts.conflicts.map((c, i) => (
                  <li key={`c${i}`}>{c}</li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-xs text-[#5A6075]">
            {a.provider === "fake" ? "Offline AI" : a.provider === "gemini" ? "Gemini" : a.provider}
            {a.model ? ` · ${a.model}` : ""} · {a.prompt_version}
            {a.latency_ms ? ` · ${(a.latency_ms / 1000).toFixed(1)} s` : ""} ·{" "}
            {timeAgo(a.created_at)}
            {a.status === "done"
              ? ". Every fact above is quoted from the message, or was chosen on the form."
              : "."}
          </p>
        </>
      )}
    </section>
  );
}

export function ScorePanel({ data }: { data: LeadAnalysis }) {
  const s = data.score;
  if (!s) return null;
  return (
    <section aria-labelledby="score-h" className={`${card} flex flex-col gap-4 p-5`}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="score-h" className="text-base font-semibold">
          Why this score
        </h2>
        <span className="text-2xl font-bold tabular-nums">
          {s.total}
          <span className="text-sm font-normal text-[#5A6075]">/100</span>
        </span>
      </div>
      {s.provisional && (
        <p className="text-sm text-[#7A4A05]">Provisional: the AI did not run for this score.</p>
      )}
      <ul className="flex flex-col gap-3">
        {s.factors.map((f) => {
          const pct = f.max ? Math.round((f.points / f.max) * 100) : 0;
          return (
            <li key={f.key} className="flex flex-col gap-1">
              <div className="flex justify-between gap-2 text-sm">
                <span className="font-semibold">{f.label}</span>
                <span className="tabular-nums text-[#3A4057]">
                  {f.points}/{f.max}
                </span>
              </div>
              <div
                role="meter"
                aria-label={f.label}
                aria-valuemin={0}
                aria-valuemax={f.max}
                aria-valuenow={f.points}
                className="h-2 overflow-hidden rounded-full bg-[#EEF0F6]"
              >
                <div className="h-full rounded-full bg-[#4338CA]" style={{ width: `${pct}%` }} />
              </div>
              <p className="text-[13px] text-[#5A6075]">{f.reason}</p>
            </li>
          );
        })}
      </ul>
      {s.caps.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-lg bg-[#FEF6F3] p-3 text-sm text-[#A32A12]">
          {s.caps.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
      <p className="text-xs text-[#5A6075]">
        Computed by Replyline&apos;s scoring rules (version {s.config_version}), not by the AI.
      </p>
    </section>
  );
}
