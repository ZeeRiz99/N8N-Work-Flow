"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonPrimary, buttonSecondary, card } from "@/components/ui-tokens";
import { api, type DuplicatePair, errorText, type MergePreview } from "@/lib/api";

export default function DuplicatesPage() {
  const me = useSession();
  const [pairs, setPairs] = useState<DuplicatePair[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{
    pairId: string;
    keepId: string;
    name: string;
    data: MergePreview;
  } | null>(null);

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
                  aria-expanded={preview?.pairId === pair.id && preview.keepId === l.id}
                  onClick={async () => {
                    try {
                      const data = await api.mergePreview(pair.id, l.id);
                      setPreview({ pairId: pair.id, keepId: l.id, name: l.full_name, data });
                    } catch (e) {
                      setMessage(errorText(e));
                    }
                  }}
                >
                  Keep this one…
                </button>
              </article>
            ))}
          </div>
          {preview?.pairId === pair.id && (
            <div className="rounded-lg border border-[#E3E6EF] p-4" aria-label="Merge preview">
              <h3 className="mb-2 font-semibold">Merge preview: keep {preview.name}</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-[#5A6075]">
                    <th className="py-1 font-semibold">Field</th>
                    <th className="py-1 font-semibold">Result</th>
                    <th className="py-1 font-semibold">From</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.data.fields.map((f) => (
                    <tr key={f.field} className="border-t border-[#EEF0F6]">
                      <td className="py-1.5 capitalize">
                        {f.field.replace("_raw", "").replace("_", " ")}
                      </td>
                      <td className="py-1.5">{f.result ?? "—"}</td>
                      <td className="py-1.5 text-[#5A6075]">
                        {f.source === "other" ? "filled from the other lead" : "kept"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-sm text-[#3A4057]">
                Moves over: {preview.data.moves.messages} message(s), {preview.data.moves.notes}{" "}
                note(s), {preview.data.moves.timeline_entries} timeline entries. The other lead is
                archived (not deleted) and the merge is written to the audit log.
                {preview.data.do_not_contact ? " Do not contact stays on." : ""}
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  className={buttonPrimary}
                  onClick={async () => {
                    await run(
                      () => api.mergeDuplicate(pair.id, preview.keepId),
                      `Merged into ${preview.name}.`,
                    );
                    setPreview(null);
                  }}
                >
                  Confirm merge
                </button>
                <button type="button" className={buttonSecondary} onClick={() => setPreview(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
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
