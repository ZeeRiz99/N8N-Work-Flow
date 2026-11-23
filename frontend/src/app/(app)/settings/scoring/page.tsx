"use client";

import { type FormEvent, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonPrimary, buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, errorText, type ScoringConfig } from "@/lib/api";

const HELP: Record<string, string> = {
  budget_fit: "Their budget against your price range for the service they want.",
  buying_intent: "How clearly they want to buy (asks for a quote, ready to hire).",
  urgency: "How soon they need it.",
  service_relevance: "Whether they want something you actually sell.",
  completeness: "Name, email, phone, company and a real message.",
  engagement: "They came back with more than one message.",
  business_fit: "Matches your ideal customer (industries below).",
};

export default function ScoringSettingsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [cfg, setCfg] = useState<ScoringConfig | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [high, setHigh] = useState(80);
  const [medium, setMedium] = useState(50);
  const [industries, setIndustries] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function apply(c: ScoringConfig) {
    setCfg(c);
    setWeights(c.weights);
    setHigh(c.thresholds.high_min);
    setMedium(c.thresholds.medium_min);
    setIndustries(c.ideal_industries.join(", "));
  }

  useEffect(() => {
    api
      .scoring()
      .then(apply)
      .catch((e) => setMessage({ ok: false, text: errorText(e) }));
  }, []);

  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const bandsOk = 0 < medium && medium < high && high <= 100;

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const saved = await api.saveScoring({
        weights,
        thresholds: { high_min: high, medium_min: medium },
        ideal_industries: industries
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      apply(saved);
      setMessage({
        ok: true,
        text: `Saved as version ${saved.version}. New and re-analyzed leads use it; existing scores keep their version.`,
      });
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) });
    } finally {
      setBusy(false);
    }
  }

  if (!cfg) {
    return message ? (
      <p role="alert" className="text-[#A32A12]">
        {message.text}
      </p>
    ) : (
      <div aria-busy="true" className="h-64 animate-pulse rounded-xl bg-[#E9ECF4]" />
    );
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">Lead scoring</h1>
        <p className="max-w-[68ch] text-[#5A6075]">
          Each lead gets 0 to 100 points from seven factors. The AI only finds facts in the message;
          these rules turn the facts into a score, so you can always see why. Version {cfg.version}.
        </p>
      </header>

      <form onSubmit={save} className="flex flex-col gap-6">
        <fieldset className={`${card} flex flex-col gap-4 p-6`} disabled={!isAdmin || busy}>
          <legend className="sr-only">Factor weights</legend>
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-base font-semibold">How much each factor counts</h2>
            <span
              aria-live="polite"
              className={`text-sm font-semibold tabular-nums ${total === 100 ? "text-[#1E6B3A]" : "text-[#A32A12]"}`}
            >
              Total {total}/100
            </span>
          </div>
          {Object.keys(cfg.labels).map((key) => (
            <div key={key} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1">
              <label htmlFor={`w-${key}`} className="font-semibold">
                {cfg.labels[key]}
              </label>
              <input
                id={`w-${key}`}
                type="number"
                min={0}
                max={100}
                step={1}
                inputMode="numeric"
                className={`${field} w-20 text-right tabular-nums`}
                value={weights[key] ?? 0}
                onChange={(e) =>
                  setWeights({
                    ...weights,
                    [key]: Math.max(0, Math.round(Number(e.target.value) || 0)),
                  })
                }
                aria-describedby={`h-${key}`}
              />
              <p id={`h-${key}`} className="col-span-2 text-[13px] text-[#5A6075]">
                {HELP[key]}
              </p>
            </div>
          ))}
          {total !== 100 && (
            <p className="text-sm text-[#A32A12]">The weights must add up to exactly 100.</p>
          )}
        </fieldset>

        <fieldset className={`${card} flex flex-col gap-4 p-6`} disabled={!isAdmin || busy}>
          <legend className="sr-only">Priority bands</legend>
          <h2 className="text-base font-semibold">Priority bands</h2>
          <div className="flex flex-wrap gap-6">
            <div className="flex flex-col gap-1">
              <label htmlFor="high" className="text-[13px] font-semibold">
                High priority from
              </label>
              <input
                id="high"
                type="number"
                min={1}
                max={100}
                className={`${field} w-24 tabular-nums`}
                value={high}
                onChange={(e) => setHigh(Math.round(Number(e.target.value) || 0))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="medium" className="text-[13px] font-semibold">
                Medium priority from
              </label>
              <input
                id="medium"
                type="number"
                min={1}
                max={99}
                className={`${field} w-24 tabular-nums`}
                value={medium}
                onChange={(e) => setMedium(Math.round(Number(e.target.value) || 0))}
              />
            </div>
          </div>
          <p className="text-[13px] text-[#5A6075]">
            {bandsOk
              ? `High: ${high} to 100 · Medium: ${medium} to ${high - 1} · Low: below ${medium}.`
              : "Medium must start below High, and High at most 100."}
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="industries" className="text-[13px] font-semibold">
              Ideal customer industries (optional, comma separated)
            </label>
            <input
              id="industries"
              className={field}
              placeholder="bakery, restaurant, clinic"
              value={industries}
              maxLength={600}
              onChange={(e) => setIndustries(e.target.value)}
            />
          </div>
        </fieldset>

        {message && (
          <p
            role={message.ok ? "status" : "alert"}
            className={`text-sm ${message.ok ? "text-[#1E6B3A]" : "text-[#A32A12]"}`}
          >
            {message.text}
          </p>
        )}
        {isAdmin ? (
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              className={buttonPrimary}
              disabled={busy || total !== 100 || !bandsOk}
            >
              {busy ? "Saving…" : "Save new version"}
            </button>
            <button
              type="button"
              className={buttonSecondary}
              disabled={busy}
              onClick={() => {
                setWeights(cfg.defaults.weights);
                setHigh(cfg.defaults.thresholds.high_min);
                setMedium(cfg.defaults.thresholds.medium_min);
              }}
            >
              Reset to recommended
            </button>
          </div>
        ) : (
          <p className="text-sm text-[#5A6075]">Only owners and admins can change scoring.</p>
        )}
      </form>
    </div>
  );
}
