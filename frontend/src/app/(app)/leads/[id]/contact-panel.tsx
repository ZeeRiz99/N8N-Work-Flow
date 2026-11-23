"use client";

import { useCallback, useEffect, useState } from "react";

import { buttonDanger, buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, type ContactRules, errorText } from "@/lib/api";

/** Contact rules, the next follow-up, and the actions that stop or schedule contact. */
export function ContactPanel({ leadId, onChanged }: { leadId: string; onChanged: () => void }) {
  const [rules, setRules] = useState<ContactRules | null>(null);
  const [when, setWhen] = useState("");
  const [open, setOpen] = useState<"schedule" | "optout" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setRules(await api.contactRules(leadId));
    } catch {
      /* the lead page shows load errors */
    }
  }, [leadId]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
      setMessage(done);
      setOpen(null);
      await load();
      onChanged();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!rules) return null;
  const failing = rules.checks.filter((c) => !c.ok);
  return (
    <section aria-labelledby="contact-h" className={`${card} flex flex-col gap-3 p-5`}>
      <h2 id="contact-h" className="text-base font-semibold">
        Contact &amp; follow-ups
      </h2>
      <p className="text-sm">
        {rules.allowed ? (
          <span className="text-[#1E6B3A]">✓ This lead can be contacted.</span>
        ) : (
          <span className="text-[#7A4A05]">
            Not contactable now: {failing.map((c) => c.label).join("; ")}.
          </span>
        )}
      </p>
      <p className="text-sm text-[#3A4057]">
        Next follow-up:{" "}
        {rules.next_follow_up_at
          ? new Date(rules.next_follow_up_at).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })
          : "none scheduled"}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={buttonSecondary}
          disabled={busy}
          onClick={() =>
            run(() => api.markReplied(leadId), "Reply logged. Automatic follow-ups stopped.")
          }
        >
          Customer replied
        </button>
        <button
          type="button"
          className={buttonSecondary}
          onClick={() => setOpen(open === "schedule" ? null : "schedule")}
        >
          Schedule follow-up
        </button>
        <button
          type="button"
          className={buttonDanger}
          onClick={() => setOpen(open === "optout" ? null : "optout")}
        >
          Opt out
        </button>
      </div>
      {open === "schedule" && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="fu-when" className="text-xs font-semibold text-[#3A4057]">
              When
            </label>
            <input
              id="fu-when"
              type="datetime-local"
              className={field}
              value={when}
              onChange={(e) => setWhen(e.target.value)}
            />
          </div>
          <button
            type="button"
            className={buttonSecondary}
            disabled={busy || !when}
            onClick={() =>
              run(
                () => api.scheduleFollowUp(leadId, new Date(when).toISOString()),
                "Follow-up scheduled. The rules are checked again when it falls due.",
              )
            }
          >
            Save
          </button>
        </div>
      )}
      {open === "optout" && (
        <div className="rounded-lg border border-[#F2C2B5] bg-[#FEF6F3] p-3 text-sm">
          <p>
            The address goes on the suppression list, open drafts and follow-ups are cancelled, and
            nothing can be sent to it again.
          </p>
          <button
            type="button"
            className={`${buttonDanger} mt-2`}
            disabled={busy}
            onClick={() => run(() => api.optOut(leadId), "Opted out. Nothing will be sent.")}
          >
            Confirm opt-out
          </button>
        </div>
      )}
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}
    </section>
  );
}
