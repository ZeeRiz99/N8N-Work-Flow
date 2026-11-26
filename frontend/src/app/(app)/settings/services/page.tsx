"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonPrimary, buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, errorText, type Service } from "@/lib/api";

// Prices are stored in minor units (cents); people type whole amounts.
const toMinor = (v: string): number | null => {
  const n = Number(v.replace(/[^0-9.]/g, ""));
  return v.trim() === "" || Number.isNaN(n) ? null : Math.round(n * 100);
};
const fromMinor = (v: number | null | undefined) => (v == null ? "" : String(v / 100));
const splitKeywords = (v: string) =>
  v
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean)
    .slice(0, 30);

function ServiceRow({
  s,
  isAdmin,
  onSave,
}: {
  s: Service;
  isAdmin: boolean;
  onSave: (id: string, body: Parameters<typeof api.updateService>[1]) => Promise<void>;
}) {
  const [name, setName] = useState(s.name);
  const [lo, setLo] = useState(fromMinor(s.price_min_minor));
  const [hi, setHi] = useState(fromMinor(s.price_max_minor));
  const [keywords, setKeywords] = useState(s.keywords.join(", "));
  const [active, setActive] = useState(s.active);
  const dirty =
    name.trim() !== s.name ||
    toMinor(lo) !== (s.price_min_minor ?? null) ||
    toMinor(hi) !== (s.price_max_minor ?? null) ||
    keywords !== s.keywords.join(", ") ||
    active !== s.active;
  const id = s.id;

  return (
    <li className="grid gap-3 border-b border-[#EEF0F6] p-4 last:border-b-0 md:grid-cols-[1.4fr_0.7fr_0.7fr]">
      <div className="flex flex-col gap-1">
        <label htmlFor={`svc-name-${id}`} className="text-xs font-semibold text-[#3A4057]">
          Service
        </label>
        <input
          id={`svc-name-${id}`}
          className={field}
          value={name}
          maxLength={120}
          disabled={!isAdmin}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`svc-lo-${id}`} className="text-xs font-semibold text-[#3A4057]">
          From ({s.currency})
        </label>
        <input
          id={`svc-lo-${id}`}
          className={field}
          inputMode="decimal"
          value={lo}
          disabled={!isAdmin}
          onChange={(e) => setLo(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`svc-hi-${id}`} className="text-xs font-semibold text-[#3A4057]">
          To ({s.currency})
        </label>
        <input
          id={`svc-hi-${id}`}
          className={field}
          inputMode="decimal"
          value={hi}
          disabled={!isAdmin}
          onChange={(e) => setHi(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1 md:col-span-2">
        <label htmlFor={`svc-kw-${id}`} className="text-xs font-semibold text-[#3A4057]">
          Words customers use (comma-separated)
        </label>
        <input
          id={`svc-kw-${id}`}
          className={field}
          value={keywords}
          disabled={!isAdmin}
          onChange={(e) => setKeywords(e.target.value)}
        />
      </div>
      <div className="flex items-end gap-3">
        <label className="flex items-center gap-2 text-sm text-[#3A4057]">
          <input
            type="checkbox"
            checked={active}
            disabled={!isAdmin}
            onChange={(e) => setActive(e.target.checked)}
          />
          Offered
        </label>
        {isAdmin && (
          <button
            type="button"
            className={buttonSecondary}
            disabled={!dirty || !name.trim()}
            onClick={() =>
              onSave(id, {
                name: name.trim(),
                price_min_minor: toMinor(lo),
                price_max_minor: toMinor(hi),
                keywords: splitKeywords(keywords),
                active,
              })
            }
          >
            Save
          </button>
        )}
      </div>
    </li>
  );
}

export default function ServicesSettingsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [services, setServices] = useState<Service[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [lo, setLo] = useState("");
  const [hi, setHi] = useState("");
  const [keywords, setKeywords] = useState("");

  const load = useCallback(async () => {
    try {
      setServices(await api.services());
    } catch (e) {
      setMessage(errorText(e));
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function save(id: string, body: Parameters<typeof api.updateService>[1]) {
    setMessage(null);
    try {
      await api.updateService(id, body);
      setMessage("Service saved.");
      await load();
    } catch (e) {
      setMessage(errorText(e));
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    setMessage(null);
    try {
      await api.addService({
        name: name.trim(),
        price_min_minor: toMinor(lo),
        price_max_minor: toMinor(hi),
        keywords: splitKeywords(keywords),
        active: true,
      });
      setMessage("Service added.");
      setName("");
      setLo("");
      setHi("");
      setKeywords("");
      await load();
    } catch (err) {
      setMessage(errorText(err));
    }
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <header>
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">Services</h1>
        <p className="text-[#5A6075]">
          What you sell and your usual price range. Scoring checks a lead&apos;s budget against
          these ranges, and reply drafts may only quote prices from this list.
        </p>
      </header>
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}
      {services.length === 0 ? (
        <p className={`${card} p-5 text-sm text-[#5A6075]`}>No services yet.</p>
      ) : (
        <ul className={`${card} flex flex-col overflow-hidden`} aria-label="Services">
          {services.map((s) => (
            <ServiceRow
              key={`${s.id}-${s.name}-${s.active}`}
              s={s}
              isAdmin={isAdmin}
              onSave={save}
            />
          ))}
        </ul>
      )}
      {isAdmin && (
        <form onSubmit={add} className={`${card} grid gap-3 p-5 md:grid-cols-[1.4fr_0.7fr_0.7fr]`}>
          <h2 className="text-base font-semibold md:col-span-3">Add a service</h2>
          <div className="flex flex-col gap-1">
            <label htmlFor="new-svc-name" className="text-xs font-semibold text-[#3A4057]">
              Service
            </label>
            <input
              id="new-svc-name"
              className={field}
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="new-svc-lo" className="text-xs font-semibold text-[#3A4057]">
              From
            </label>
            <input
              id="new-svc-lo"
              className={field}
              inputMode="decimal"
              value={lo}
              onChange={(e) => setLo(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="new-svc-hi" className="text-xs font-semibold text-[#3A4057]">
              To
            </label>
            <input
              id="new-svc-hi"
              className={field}
              inputMode="decimal"
              value={hi}
              onChange={(e) => setHi(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1 md:col-span-2">
            <label htmlFor="new-svc-kw" className="text-xs font-semibold text-[#3A4057]">
              Words customers use (comma-separated)
            </label>
            <input
              id="new-svc-kw"
              className={field}
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <button type="submit" className={buttonPrimary}>
              Add service
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
