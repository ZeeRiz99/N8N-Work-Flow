"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { AskPanel } from "@/components/ask-panel";
import { PriorityBadge } from "@/components/badges";
import { buttonPrimary, card, field } from "@/components/ui-tokens";
import { api, errorText, type LeadRow, type PlaygroundResult } from "@/lib/api";

const LABELS: Record<string, string> = {
  budget_fit: "Budget fit",
  buying_intent: "Buying intent",
  urgency: "Urgency",
  service_relevance: "Service relevance",
  completeness: "Completeness",
  engagement: "Engagement",
  business_fit: "Business fit",
};
const SAMPLE =
  "Hi! We run a small bakery and need a new website with online ordering. Our budget is " +
  "around $2,000 and we'd love it live within a month. Could you send a quote?";

function Playground() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await api.analyzeText(text));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const f = result?.facts;
  return (
    <div className="flex flex-wrap items-start gap-6">
      <form onSubmit={run} className={`${card} flex min-w-0 flex-[3_1_420px] flex-col gap-3 p-6`}>
        <div>
          <h2 className="text-base font-semibold">Analyze a message</h2>
          <p className="text-[13px] text-[#5A6075]">
            Paste any inquiry to see what the AI finds and how it would score. Nothing is saved.
          </p>
        </div>
        <label htmlFor="pg-text" className="sr-only">
          Message to analyze
        </label>
        <textarea
          id="pg-text"
          rows={9}
          maxLength={8000}
          className={`${field} py-2 leading-relaxed`}
          placeholder="Paste a customer message here"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <button type="submit" className={buttonPrimary} disabled={busy || !text.trim()}>
            {busy ? "Analyzing…" : "Analyze"}
          </button>
          <button
            type="button"
            className="text-sm font-semibold text-[#4338CA] underline"
            onClick={() => setText(SAMPLE)}
          >
            Use an example
          </button>
        </div>
        {error && <p className="text-sm text-[#A32A12]">{error}</p>}
      </form>

      <section
        aria-live="polite"
        className={`${card} flex min-w-0 flex-[2_1_320px] flex-col gap-3 p-6`}
      >
        <h2 className="text-base font-semibold">Result</h2>
        {!result ? (
          <p className="text-sm text-[#5A6075]">Run an analysis to see facts and a score.</p>
        ) : (
          <>
            {result.note && (
              <p className="rounded-lg border border-[#F5D7A8] bg-[#FFF8EC] p-3 text-sm text-[#7A4A05]">
                {result.note}
              </p>
            )}
            {result.guard_flags.length > 0 && (
              <p className="rounded-lg border border-[#F2C2B5] bg-[#FEF6F3] p-3 text-sm text-[#A32A12]">
                This text tries to instruct the AI. It was treated as data and flagged for review.
              </p>
            )}
            <div className="flex items-center gap-3">
              <span className="text-3xl font-bold tabular-nums">{result.score.total}</span>
              <PriorityBadge priority={result.score.band} />
              {result.score.provisional && (
                <span className="text-sm text-[#7A4A05]">provisional</span>
              )}
            </div>
            {result.summary && <p className="text-sm">{result.summary}</p>}
            {f && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-[#5A6075]">Services</dt>
                <dd>{f.services.map((s) => s.name).join(", ") || "None found"}</dd>
                <dt className="text-[#5A6075]">Budget</dt>
                <dd>{f.budget?.evidence ? `“${f.budget.evidence}”` : "Not stated"}</dd>
                <dt className="text-[#5A6075]">Timeline</dt>
                <dd>{f.timeline.evidence ? `“${f.timeline.evidence}”` : "Not stated"}</dd>
                <dt className="text-[#5A6075]">Intent</dt>
                <dd>{result.intent?.replace("_", " ") ?? "Not judged"}</dd>
              </dl>
            )}
            <ul className="flex flex-col gap-1 text-[13px]">
              {result.score.factors.map((x) => (
                <li key={x.key} className="flex justify-between gap-3">
                  <span>{LABELS[x.key] ?? x.key}</span>
                  <span className="tabular-nums text-[#3A4057]">
                    {x.points}/{x.max}
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-[#5A6075]">
              Not saved. Scored with your services and your scoring settings.
            </p>
          </>
        )}
      </section>
    </div>
  );
}

function LeadTools() {
  const [query, setQuery] = useState("");
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [chosen, setChosen] = useState<LeadRow | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .leads({ q: query || undefined, sort: "score", page: 1 })
        .then((p) => setLeads(p.items.slice(0, 8)))
        .catch(() => undefined);
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="flex flex-wrap items-start gap-6">
      <section className={`${card} flex min-w-0 flex-[2_1_300px] flex-col gap-3 p-6`}>
        <h2 className="text-base font-semibold">Choose a lead</h2>
        <label htmlFor="lead-q" className="sr-only">
          Search leads
        </label>
        <input
          id="lead-q"
          type="search"
          className={field}
          placeholder="Name, company or email"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <ul className="flex flex-col">
          {leads.map((l) => (
            <li key={l.id}>
              <button
                type="button"
                onClick={() => setChosen(l)}
                aria-pressed={chosen?.id === l.id}
                className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left ${chosen?.id === l.id ? "bg-[#EEF0FF]" : "hover:bg-[#F6F7FB]"}`}
              >
                <span>
                  <span className="block font-medium">{l.full_name}</span>
                  <span className="block text-xs text-[#5A6075]">{l.company ?? l.email}</span>
                </span>
                <PriorityBadge priority={l.priority} />
              </button>
            </li>
          ))}
          {leads.length === 0 && <li className="text-sm text-[#5A6075]">No leads found.</li>}
        </ul>
      </section>
      <div className="flex min-w-0 flex-[3_1_420px] flex-col gap-4">
        {!chosen ? (
          <div className={`${card} p-6 text-sm text-[#5A6075]`}>
            Pick a lead to ask questions about it, see its summary, or write a reply.
          </div>
        ) : (
          <>
            <div className={`${card} flex flex-wrap items-center justify-between gap-3 p-5`}>
              <div>
                <p className="font-semibold">{chosen.full_name}</p>
                <p className="text-sm text-[#5A6075]">
                  {chosen.latest_message || "No message yet."}
                </p>
              </div>
              <Link href={`/leads/${chosen.id}`} className="text-sm font-semibold text-[#4338CA]">
                Open lead, summary and reply draft →
              </Link>
            </div>
            <AskPanel key={chosen.id} leadId={chosen.id} />
          </>
        )}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const [tab, setTab] = useState<"playground" | "lead">("playground");
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">AI Assistant</h1>
        <p className="text-[#5A6075]">Drafts only: nothing is sent automatically.</p>
      </header>
      <div role="tablist" aria-label="Assistant tools" className="flex gap-2">
        {(
          [
            ["playground", "Analyze text"],
            ["lead", "Ask about a lead"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold ${tab === key ? "bg-[#EEF0FF] text-[#3730A3]" : "text-[#3A4057] hover:bg-[#F6F7FB]"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">{tab === "playground" ? <Playground /> : <LeadTools />}</div>
    </div>
  );
}
