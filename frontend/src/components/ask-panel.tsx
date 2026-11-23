"use client";

import { type FormEvent, useState } from "react";

import { buttonPrimary, card, field } from "@/components/ui-tokens";
import { api, type AskResult, errorText } from "@/lib/api";

const EXAMPLES = ["What is their budget?", "When do they need it?", "What did they ask for?"];

/** Ask a question answered only from one lead's own records, with the records it used. */
export function AskPanel({ leadId, compact }: { leadId: string; compact?: boolean }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    if (q.trim().length < 2) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.ask(leadId, q.trim()));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-labelledby={`ask-h-${leadId}`}
      className={`${card} flex flex-col gap-3 ${compact ? "p-5" : "p-6"}`}
    >
      <div>
        <h2 id={`ask-h-${leadId}`} className="text-base font-semibold">
          Ask about this lead
        </h2>
        <p className="text-[13px] text-[#5A6075]">
          Answers come only from this lead&apos;s messages, notes and history. Read-only.
        </p>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <label htmlFor={`ask-${leadId}`} className="sr-only">
          Your question
        </label>
        <input
          id={`ask-${leadId}`}
          className={`${field} min-w-0 flex-1`}
          placeholder="e.g. What is their budget?"
          value={question}
          maxLength={500}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" className={buttonPrimary} disabled={busy}>
          {busy ? "…" : "Ask"}
        </button>
      </form>
      {!result && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              className="rounded-full border border-[#E3E6EF] px-3 py-1 text-xs text-[#3A4057] hover:bg-[#F6F7FB]"
              onClick={() => {
                setQuestion(q);
                ask(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-[#A32A12]">
          {error}
        </p>
      )}
      {result && (
        <div aria-live="polite" className="flex flex-col gap-2 rounded-lg bg-[#F6F7FB] p-4">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.answer}</p>
          {result.citations.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-[#5A6075]">From:</span>
              {result.citations.map((c) => (
                <span key={c.id} className="rounded-full bg-white px-2 py-0.5 text-[#3A4057]">
                  {c.label}
                </span>
              ))}
            </div>
          )}
          {!result.supported && (
            <p className="text-xs text-[#7A4A05]">
              No record was cited for this answer. Check it before relying on it.
            </p>
          )}
          <p className="text-xs text-[#5A6075]">
            {result.note ??
              (result.source === "gemini"
                ? `Gemini · ${result.model}`
                : result.source === "fake"
                  ? "Offline AI"
                  : "Keyword search")}
          </p>
        </div>
      )}
    </section>
  );
}
