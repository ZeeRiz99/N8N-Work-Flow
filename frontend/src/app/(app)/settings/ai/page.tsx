"use client";

import { type FormEvent, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonPrimary, card, field } from "@/components/ui-tokens";
import { type AISettings, api, errorText } from "@/lib/api";

const STYLES = [
  ["professional", "Professional"],
  ["friendly", "Friendly"],
  ["concise", "Concise"],
  ["sales", "Sales"],
];

export default function AISettingsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [s, setS] = useState<AISettings | null>(null);
  const [style, setStyle] = useState("professional");
  const [cap, setCap] = useState(0);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .aiSettings()
      .then((x) => {
        setS(x);
        setStyle(x.default_style);
        setCap(x.daily_cap);
      })
      .catch((e) => setMessage({ ok: false, text: errorText(e) }));
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const x = await api.saveAiSettings({ default_style: style, daily_cap: cap });
      setS(x);
      setMessage({ ok: true, text: "AI settings saved." });
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) });
    } finally {
      setBusy(false);
    }
  }

  if (!s) {
    return <div aria-busy="true" className="h-48 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  }
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">AI settings</h1>
        <p className="text-[#5A6075]">
          The AI reads inquiries and writes drafts. It never sends anything or changes a score by
          itself.
        </p>
      </header>
      <form onSubmit={save} className={`${card} flex flex-col gap-5 p-6`}>
        <fieldset disabled={!isAdmin || busy} className="flex flex-col gap-5">
          <legend className="sr-only">AI settings</legend>
          <div className="flex flex-col gap-1">
            <label htmlFor="ai-style" className="text-[13px] font-semibold">
              Default reply style
            </label>
            <select
              id="ai-style"
              className={`${field} max-w-xs`}
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            >
              {STYLES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="ai-cap" className="text-[13px] font-semibold">
              Daily limit for AI analyses
            </label>
            <input
              id="ai-cap"
              type="number"
              min={0}
              max={s.server_max_daily_cap}
              className={`${field} w-32 tabular-nums`}
              value={cap}
              onChange={(e) => setCap(Math.max(0, Math.round(Number(e.target.value) || 0)))}
              aria-describedby="ai-cap-help"
            />
            <p id="ai-cap-help" className="text-[13px] text-[#5A6075]">
              Up to {s.server_max_daily_cap}. Past the limit, new leads get a provisional score and
              are analyzed later; no lead is lost. Set 0 to pause AI analysis.
            </p>
          </div>
        </fieldset>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg bg-[#F6F7FB] p-4 text-sm">
          <dt className="text-[#5A6075]">Provider</dt>
          <dd>{s.provider === "gemini" ? "Google Gemini" : "Offline AI (no external calls)"}</dd>
          <dt className="text-[#5A6075]">Model</dt>
          <dd>{s.model}</dd>
        </dl>
        {message && (
          <p
            role={message.ok ? "status" : "alert"}
            className={`text-sm ${message.ok ? "text-[#1E6B3A]" : "text-[#A32A12]"}`}
          >
            {message.text}
          </p>
        )}
        {isAdmin ? (
          <div>
            <button type="submit" className={buttonPrimary} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        ) : (
          <p className="text-sm text-[#5A6075]">Only owners and admins can change AI settings.</p>
        )}
      </form>
    </div>
  );
}
