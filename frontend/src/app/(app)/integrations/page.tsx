"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonSecondary, card } from "@/components/ui-tokens";
import { api, errorText, type Integration } from "@/lib/api";

export default function IntegrationsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [items, setItems] = useState<Integration[] | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; detail: string }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .integrations()
      .then(setItems)
      .catch((e) => setError(errorText(e)));
  }, []);

  async function test(kind: string) {
    setBusy(kind);
    try {
      const r = await api.testIntegration(kind);
      setResults((x) => ({ ...x, [kind]: r }));
    } catch (e) {
      setResults((x) => ({ ...x, [kind]: { ok: false, detail: errorText(e) } }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <header>
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">Integrations</h1>
        <p className="text-[#5A6075]">The services Replyline uses, and whether they answer.</p>
      </header>
      {error && (
        <p role="alert" className="text-[#A32A12]">
          {error}
        </p>
      )}
      {!items && !error && (
        <div aria-busy="true" className="h-48 animate-pulse rounded-xl bg-[#E9ECF4]" />
      )}
      <ul className="flex flex-col gap-3">
        {items?.map((i) => {
          const r = results[i.kind];
          return (
            <li
              key={i.kind}
              className={`${card} flex flex-wrap items-center justify-between gap-3 p-5`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="font-semibold">{i.name}</h2>
                  <span
                    className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                    style={
                      i.configured
                        ? { color: "#1E6B3A", background: "#E3F4E9" }
                        : { color: "#7A4A05", background: "#FDF0C8" }
                    }
                  >
                    {i.configured ? "Set up" : "Not set up"}
                  </span>
                </div>
                <p className="mt-1 text-sm text-[#5A6075]">{i.detail}</p>
                {r && (
                  <p
                    role="status"
                    className="mt-1 text-sm font-medium"
                    style={{ color: r.ok ? "#1E6B3A" : "#A32A12" }}
                  >
                    {r.ok ? "✓ " : "✗ "}
                    {r.detail}
                  </p>
                )}
              </div>
              {isAdmin && (
                <button
                  type="button"
                  className={buttonSecondary}
                  disabled={busy !== null || (!i.configured && i.kind === "telegram")}
                  onClick={() => test(i.kind)}
                >
                  {busy === i.kind ? "Testing…" : "Test connection"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
