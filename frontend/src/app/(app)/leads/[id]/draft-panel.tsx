"use client";

import { useEffect, useState } from "react";

import { buttonPrimary, buttonSecondary, card, field } from "@/components/ui-tokens";
import {
  api,
  ApiError,
  type Draft,
  type DraftCheck,
  errorText,
  type FollowUpStatus,
} from "@/lib/api";

const STYLES = [
  ["professional", "Professional"],
  ["friendly", "Friendly"],
  ["concise", "Concise"],
  ["sales", "Sales"],
] as const;
const OPT_OUT = `If you'd rather not hear from us again, just reply "unsubscribe".`;

function Checks({ checks }: { checks: DraftCheck[] }) {
  return (
    <ul aria-label="Automatic checks" className="flex flex-col gap-1.5 text-sm">
      {checks.map((c) => {
        const tone = c.ok ? "#1E6B3A" : c.severity === "warn" ? "#7A4A05" : "#A32A12";
        return (
          <li key={c.key} className="flex gap-2">
            <span aria-hidden="true" style={{ color: tone }} className="font-bold">
              {c.ok ? "✓" : c.severity === "warn" ? "!" : "✗"}
            </span>
            <span>
              <span className="sr-only">{c.ok ? "Passed: " : "Problem: "}</span>
              {c.label}
              {c.detail && !c.ok && <span className="text-[#5A6075]"> · {c.detail}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function DraftPanel({ leadId, disabled }: { leadId: string; disabled?: string }) {
  const [style, setStyle] = useState<string>("");
  const [kind, setKind] = useState<"first_reply" | "follow_up">("first_reply");
  const [followUp, setFollowUp] = useState<FollowUpStatus | null>(null);
  const [defaultStyle, setDefaultStyle] = useState("professional");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [checks, setChecks] = useState<DraftCheck[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api
      .aiSettings()
      .then((s) => setDefaultStyle(s.default_style))
      .catch(() => undefined);
    api
      .followUp(leadId)
      .then(setFollowUp)
      .catch(() => undefined);
  }, [leadId]);

  const followUpBlocked = kind === "follow_up" && followUp !== null && !followUp.eligible;

  async function generate() {
    setBusy(true);
    setMessage(null);
    try {
      const d = await api.generateDraft(leadId, style || null, kind);
      setDraft(d);
      setSubject(d.subject);
      setBody(d.body.replace(OPT_OUT, "").trimEnd());
      setChecks(d.checks);
      setDirty(false);
    } catch (e) {
      setMessage(e instanceof ApiError && e.status === 409 ? e.message : errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function recheck() {
    if (!draft) return;
    setBusy(true);
    try {
      const r = await api.checkDraft(leadId, subject, body, draft.services_mentioned);
      setChecks(r.checks);
      setDirty(false);
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}\n\n${OPT_OUT}`);
      setMessage("Copied to the clipboard.");
    } catch {
      setMessage("Could not copy. Select the text and copy it by hand.");
    }
  }

  const failing = checks.filter((c) => !c.ok && c.severity === "fail").length;

  return (
    <section aria-labelledby="draft-h" className={`${card} flex flex-col gap-4 p-6`}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="draft-h" className="text-base font-semibold">
            Reply draft
          </h2>
          <p className="text-[13px] text-[#5A6075]">
            Preview only: nothing is saved or sent. Approval and sending come with the Approvals
            screen.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="draft-kind" className="text-xs font-semibold text-[#3A4057]">
              Type
            </label>
            <select
              id="draft-kind"
              className={field}
              value={kind}
              onChange={(e) => setKind(e.target.value as typeof kind)}
            >
              <option value="first_reply">First reply</option>
              <option value="follow_up">Follow-up</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="draft-style" className="text-xs font-semibold text-[#3A4057]">
              Style
            </label>
            <select
              id="draft-style"
              className={field}
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            >
              <option value="">
                Default ({STYLES.find(([v]) => v === defaultStyle)?.[1] ?? defaultStyle})
              </option>
              {STYLES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className={buttonPrimary}
            disabled={busy || !!disabled || followUpBlocked}
            onClick={generate}
          >
            {busy && !draft ? "Writing…" : draft ? "Write again" : "Write a draft"}
          </button>
        </div>
      </div>
      {disabled && <p className="text-sm text-[#5A6075]">{disabled}</p>}
      {kind === "follow_up" && followUp && (
        <div className="rounded-lg bg-[#F6F7FB] p-4 text-sm">
          <p className="mb-1.5 font-semibold">
            {followUp.eligible ? "A follow-up is appropriate now" : "Not time for a follow-up yet"}
          </p>
          <ul className="flex flex-col gap-1">
            {followUp.checks.map((c) => (
              <li key={c.key} className="flex gap-2">
                <span
                  aria-hidden="true"
                  className="font-bold"
                  style={{ color: c.ok ? "#1E6B3A" : "#A32A12" }}
                >
                  {c.ok ? "✓" : "✗"}
                </span>
                <span>
                  <span className="sr-only">{c.ok ? "Met: " : "Not met: "}</span>
                  {c.label}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-[#5A6075]">
            Replyline decides this with fixed rules; the AI only writes the wording. Customer
            replies are not tracked yet.
          </p>
        </div>
      )}
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}

      {draft && (
        <>
          {draft.note && (
            <p className="rounded-lg border border-[#F5D7A8] bg-[#FFF8EC] p-3 text-sm text-[#7A4A05]">
              {draft.note}
            </p>
          )}
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-[#3A4057]">To</span>
            <span className="text-sm">{draft.to ?? "No email address"}</span>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="draft-subject" className="text-xs font-semibold text-[#3A4057]">
              Subject
            </label>
            <input
              id="draft-subject"
              className={field}
              value={subject}
              maxLength={200}
              onChange={(e) => {
                setSubject(e.target.value);
                setDirty(true);
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="draft-body" className="text-xs font-semibold text-[#3A4057]">
              Message
            </label>
            <textarea
              id="draft-body"
              rows={11}
              className={`${field} py-2 leading-relaxed`}
              value={body}
              maxLength={6000}
              onChange={(e) => {
                setBody(e.target.value);
                setDirty(true);
              }}
            />
            <p className="text-xs text-[#5A6075]">Added automatically: {OPT_OUT}</p>
          </div>
          <div className="rounded-lg bg-[#F6F7FB] p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">
                Automatic checks{" "}
                <span className={failing ? "text-[#A32A12]" : "text-[#1E6B3A]"}>
                  {failing ? `· ${failing} to fix` : "· all passed"}
                </span>
              </h3>
              {dirty && (
                <button type="button" className={buttonSecondary} disabled={busy} onClick={recheck}>
                  Check again
                </button>
              )}
            </div>
            <Checks checks={checks} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className={buttonSecondary} onClick={copy}>
              Copy draft
            </button>
            <span className="text-xs text-[#5A6075]">
              {draft.source === "template"
                ? "Written from a template"
                : draft.source === "fake"
                  ? "Written by the offline AI"
                  : `Written by Gemini · ${draft.model}`}{" "}
              · {draft.prompt_version}
            </span>
          </div>
        </>
      )}
    </section>
  );
}
