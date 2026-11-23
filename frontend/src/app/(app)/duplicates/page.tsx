"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonPrimary, buttonSecondary, card } from "@/components/ui-tokens";
import { api, type DuplicatePair, errorText } from "@/lib/api";

export default function DuplicatesPage() {
  const me = useSession();
  const [pairs, setPairs] = useState<DuplicatePair[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setPairs(await api.duplicates());
    } catch (e) {
      setMessage(errorText(e));
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    try {
      await fn();
      setMessage(done);
      await load();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const isAdmin = me.role === "owner" || me.role === "admin";

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">
            Possible duplicates
          </h1>
          <p className="mt-1 max-w-[62ch] text-[#5A6075]">
            Leads with very similar names and companies. Same email or phone is merged
            automatically; these need a person to decide. Nothing is merged until you choose.
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            className={buttonSecondary}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const r = await api.scanDuplicates();
                setMessage(`Scan finished: ${r.added} new pair(s) found.`);
              }, "Scan finished.")
            }
          >
            Scan for duplicates
          </button>
        )}
      </header>
      {message && (
        <p role="status" className="rounded-lg bg-[#F3F4FA] px-4 py-2.5 text-sm text-[#3A4057]">
          {message}
        </p>
      )}
      {pairs === null && (
        <div aria-busy="true" className="h-32 animate-pulse rounded-xl bg-[#E9ECF4]" />
      )}
      {pairs?.length === 0 && (
        <div className={`${card} p-8 text-center`}>
          <p className="font-semibold">No possible duplicates</p>
          <p className="mt-1 text-sm text-[#5A6075]">
            {isAdmin ? "Run a scan after importing or adding many leads." : "Nothing to review."}
          </p>
        </div>
      )}
      {pairs?.map((pair) => (
        <section
          key={pair.id}
          className={`${card} flex flex-col gap-4 p-5`}
          aria-label="Duplicate pair"
        >
          <p className="text-sm text-[#3A4057]">
            {Math.round(pair.confidence * 100)}% similar ·{" "}
            {pair.reasons
              .map(
                (r) =>
                  `${r.field === "full_name" ? "name" : r.field} ${Math.round(r.similarity * 100)}%`,
              )
              .join(", ")}
          </p>
          <div className="flex flex-wrap gap-4">
            {pair.leads.map((l) => (
              <article
                key={l.id}
                className="flex min-w-[240px] flex-1 flex-col gap-1 rounded-lg bg-[#F6F7FB] p-4"
              >
                <Link href={`/leads/${l.id}`} className="font-semibold">
                  {l.full_name}
                </Link>
                <span className="text-sm">{l.company ?? "No company"}</span>
                <span className="text-sm text-[#3A4057]">{l.email ?? "No email"}</span>
                <span className="text-sm text-[#3A4057]">{l.phone ?? "No phone"}</span>
                <span className="text-xs text-[#5A6075]">
                  Added {new Date(l.created_at).toLocaleDateString()}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  className={`${buttonPrimary} mt-2`}
                  onClick={() =>
                    run(() => api.mergeDuplicate(pair.id, l.id), `Merged into ${l.full_name}.`)
                  }
                >
                  Keep this one
                </button>
              </article>
            ))}
          </div>
          <div>
            <button
              type="button"
              disabled={busy}
              className={buttonSecondary}
              onClick={() => run(() => api.dismissDuplicate(pair.id), "Marked as not duplicates.")}
            >
              Not duplicates
            </button>
          </div>
        </section>
      ))}
    </div>
  );
}
