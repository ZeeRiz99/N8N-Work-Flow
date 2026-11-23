"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonDanger, buttonPrimary, card, field } from "@/components/ui-tokens";
import { api, errorText, type NotificationSettings } from "@/lib/api";

export default function RulesSettingsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [n, setN] = useState<NotificationSettings | null>(null);
  const [fu, setFu] = useState<{
    max_attempts: number;
    cooldown_days: number;
    timezone: string;
    business_hours: string;
  } | null>(null);
  const [days, setDays] = useState<string>("");
  const [due, setDue] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.notifications(), api.followUpSettings(), api.retention()])
      .then(([a, b, c]) => {
        setN(a);
        setFu(b);
        setDays(c.erase_archived_after_days ? String(c.erase_archived_after_days) : "");
        setDue(c.due_for_erasure);
      })
      .catch((e) => setMessage(errorText(e)));
  }, []);

  async function run(fn: () => Promise<unknown>, done: string) {
    setMessage(null);
    try {
      await fn();
      setMessage(done);
    } catch (e) {
      setMessage(errorText(e));
    }
  }

  if (!n || !fu)
    return <div aria-busy="true" className="h-48 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  const toggle = (key: keyof NotificationSettings, label: string) => (
    <label className="flex items-center gap-3 text-sm">
      <input
        type="checkbox"
        className="h-5 w-5"
        checked={Boolean(n[key])}
        disabled={!isAdmin}
        onChange={(e) => setN({ ...n, [key]: e.target.checked })}
      />
      {label}
    </label>
  );

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">Rules &amp; data</h1>
        <p className="text-[#5A6075]">Notifications, follow-up limits and how long data is kept.</p>
      </header>
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}

      <section className={`${card} flex flex-col gap-3 p-6`}>
        <h2 className="font-semibold">Notifications</h2>
        {toggle("alert_on_high", "Alert the team about high-priority leads")}
        {toggle("daily_report", "Daily summary at 08:30")}
        {toggle("weekly_report", "Weekly lead-source report on Mondays")}
        <div className="flex flex-col gap-1">
          <label htmlFor="alert-email" className="text-xs font-semibold text-[#3A4057]">
            Team email for alerts and reports
          </label>
          <input
            id="alert-email"
            type="email"
            className={`${field} max-w-sm`}
            value={n.alert_email ?? ""}
            disabled={!isAdmin}
            onChange={(e) => setN({ ...n, alert_email: e.target.value || null })}
          />
        </div>
        {isAdmin && (
          <div>
            <button
              type="button"
              className={buttonPrimary}
              onClick={() => run(() => api.saveNotifications(n), "Notifications saved.")}
            >
              Save notifications
            </button>
          </div>
        )}
      </section>

      <section className={`${card} flex flex-col gap-3 p-6`}>
        <h2 className="font-semibold">Follow-up rules</h2>
        <p className="text-sm text-[#5A6075]">
          Follow-ups are prepared {fu.business_hours} ({fu.timezone}). A reply, an opt-out or the
          do-not-contact flag always stops them.
        </p>
        <div className="flex flex-wrap gap-6">
          <div className="flex flex-col gap-1">
            <label htmlFor="max-att" className="text-xs font-semibold text-[#3A4057]">
              Emails per lead, at most
            </label>
            <input
              id="max-att"
              type="number"
              min={1}
              max={6}
              className={`${field} w-24`}
              value={fu.max_attempts}
              disabled={!isAdmin}
              onChange={(e) => setFu({ ...fu, max_attempts: Number(e.target.value) || 1 })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="cooldown" className="text-xs font-semibold text-[#3A4057]">
              Days between emails, at least
            </label>
            <input
              id="cooldown"
              type="number"
              min={1}
              max={60}
              className={`${field} w-24`}
              value={fu.cooldown_days}
              disabled={!isAdmin}
              onChange={(e) => setFu({ ...fu, cooldown_days: Number(e.target.value) || 1 })}
            />
          </div>
        </div>
        {isAdmin && (
          <div>
            <button
              type="button"
              className={buttonPrimary}
              onClick={() =>
                run(
                  () => api.saveFollowUpSettings(fu.max_attempts, fu.cooldown_days),
                  "Follow-up rules saved.",
                )
              }
            >
              Save follow-up rules
            </button>
          </div>
        )}
      </section>

      <section className={`${card} flex flex-col gap-3 p-6`}>
        <h2 className="font-semibold">Data retention</h2>
        <p className="text-sm text-[#5A6075]">
          Erase archived leads after a number of days (minimum 30). Erasing removes the lead and
          everything attached; the audit log keeps only that it happened. You can also erase a
          single lead from its page at any time.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="ret-days" className="text-xs font-semibold text-[#3A4057]">
              Erase archived leads after (days)
            </label>
            <input
              id="ret-days"
              type="number"
              min={30}
              max={3650}
              placeholder="Keep forever"
              className={`${field} w-40`}
              value={days}
              disabled={!isAdmin}
              onChange={(e) => setDays(e.target.value)}
            />
          </div>
          {isAdmin && (
            <button
              type="button"
              className={buttonPrimary}
              onClick={() =>
                run(async () => {
                  const r = await api.saveRetention(days ? Number(days) : null);
                  setDue(r.due_for_erasure);
                }, "Retention saved.")
              }
            >
              Save
            </button>
          )}
        </div>
        {isAdmin && due > 0 && (
          <div className="rounded-lg border border-[#F2C2B5] bg-[#FEF6F3] p-3 text-sm">
            <p>{due} archived lead(s) are past the retention period.</p>
            <button
              type="button"
              className={`${buttonDanger} mt-2`}
              onClick={() => {
                if (window.confirm(`Erase ${due} archived lead(s) permanently?`)) {
                  run(async () => {
                    await api.purgeArchived();
                    setDue(0);
                  }, "Archived leads erased.");
                }
              }}
            >
              Erase them now
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
