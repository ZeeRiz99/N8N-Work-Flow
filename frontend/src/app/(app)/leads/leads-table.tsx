"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AiStatusPill, PriorityBadge } from "@/components/badges";
import { useSession } from "@/components/session";
import { buttonPrimary, buttonSecondary, card, field, timeAgo } from "@/components/ui-tokens";
import {
  api,
  AuthRequired,
  errorText,
  type LeadFilters,
  type LeadRow,
  type Member,
  type Page,
  type Source,
  type Stage,
} from "@/lib/api";

const POLL_FAST_MS = 2000; // while any lead is still being analyzed
const POLL_SLOW_MS = 15000;
const PAGE_SIZE = 25;

function Select({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-[130px] flex-1 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-semibold text-[#3A4057]">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={field}>
        {children}
      </select>
    </div>
  );
}

export function LeadsTable() {
  const me = useSession();
  const router = useRouter();
  const [filters, setFilters] = useState<LeadFilters>({ sort: "recent", page: 1 });
  const [search, setSearch] = useState("");
  const [data, setData] = useState<Page<LeadRow> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    Promise.all([api.stages(), api.sources(), api.members()])
      .then(([st, so, mem]) => {
        setStages(st);
        setSources(so);
        setMembers(mem);
      })
      .catch(() => undefined);
  }, []);

  // Wait until typing pauses before searching.
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, q: search || undefined, page: 1 })), 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    try {
      setData(await api.leads({ ...filters, page_size: PAGE_SIZE }));
      setError(null);
    } catch (e) {
      if (e instanceof AuthRequired) {
        router.replace("/login?next=/leads");
        return;
      }
      setError(errorText(e));
    }
  }, [filters, router]);

  const busy = data?.items.some((l) => l.ai_status === "pending" || l.ai_status === "processing");

  useEffect(() => {
    const first = setTimeout(load, 0);
    const timer = setInterval(load, busy ? POLL_FAST_MS : POLL_SLOW_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [load, busy]);

  const set = (patch: Partial<LeadFilters>) => setFilters((f) => ({ ...f, ...patch, page: 1 }));
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const isAdmin = me.role === "owner" || me.role === "admin";
  const filtered = Boolean(filters.q || filters.stage || filters.priority || filters.source);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-tight font-bold tracking-tight">Leads</h1>
          <p className="mt-1 text-[#5A6075]">
            {data ? `${data.total} ${data.total === 1 ? "lead" : "leads"}` : "Loading…"}
            {busy ? " · updating while AI works" : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/leads/import" className={buttonSecondary}>
            Import CSV
          </Link>
          {isAdmin && (
            <a href={api.exportUrl} className={buttonSecondary} download>
              Export
            </a>
          )}
          <button type="button" className={buttonPrimary} onClick={() => setAdding(true)}>
            New lead
          </button>
        </div>
      </header>

      <section aria-label="Filters" className={`${card} flex flex-wrap items-end gap-3 p-4`}>
        <div className="flex min-w-[220px] flex-[2] flex-col gap-1">
          <label htmlFor="lead-search" className="text-xs font-semibold text-[#3A4057]">
            Search
          </label>
          <input
            id="lead-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name, company or email"
            className={field}
          />
        </div>
        <Select
          id="f-stage"
          label="Stage"
          value={filters.stage ?? ""}
          onChange={(v) => set({ stage: v || undefined })}
        >
          <option value="">All stages</option>
          {stages.map((s) => (
            <option key={s.id} value={s.key}>
              {s.label}
            </option>
          ))}
        </Select>
        <Select
          id="f-priority"
          label="Priority"
          value={filters.priority ?? ""}
          onChange={(v) => set({ priority: v || undefined })}
        >
          <option value="">All</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="unscored">Not scored</option>
        </Select>
        <Select
          id="f-source"
          label="Source"
          value={filters.source ?? ""}
          onChange={(v) => set({ source: v || undefined })}
        >
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s.id} value={s.key}>
              {s.label}
            </option>
          ))}
        </Select>
        <Select
          id="f-assigned"
          label="Assigned to"
          value={filters.assigned ?? ""}
          onChange={(v) => set({ assigned: v || undefined })}
        >
          <option value="">Anyone</option>
          <option value="me">Me</option>
          <option value="none">Unassigned</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.full_name}
            </option>
          ))}
        </Select>
        <Select
          id="f-sort"
          label="Sort"
          value={filters.sort ?? "recent"}
          onChange={(v) => set({ sort: v as LeadFilters["sort"] })}
        >
          <option value="recent">Latest activity</option>
          <option value="newest">Newest first</option>
          <option value="score">Highest score</option>
          <option value="name">Name A–Z</option>
        </Select>
      </section>

      {error && !data && (
        <div role="alert" className="rounded-xl border border-[#F2C2B5] bg-[#FEF6F3] p-5">
          <p className="font-semibold text-[#A32A12]">Could not load leads</p>
          <p className="mt-1 text-sm text-[#3A4057]">{error}</p>
          <button type="button" onClick={load} className={`${buttonSecondary} mt-3`}>
            Try again
          </button>
        </div>
      )}

      {!data && !error && (
        <div aria-busy="true" className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-[#E9ECF4]" />
          ))}
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className={`${card} p-8 text-center`}>
          <p className="font-semibold">{filtered ? "No leads match" : "No leads yet"}</p>
          <p className="mt-1 text-sm text-[#5A6075]">
            {filtered
              ? "Try a different search or clear the filters."
              : "Submit the public form, import a CSV, or add a lead by hand."}
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <section className={`${card} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs font-semibold text-[#5A6075]">
                  {[
                    "Lead",
                    "Latest message",
                    "Score",
                    "Priority",
                    "Stage",
                    "Assigned",
                    "Activity",
                  ].map((h) => (
                    <th key={h} scope="col" className="px-4 py-2.5">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((lead) => (
                  <tr key={lead.id} className="border-b border-[#EEF0F6] align-top last:border-0">
                    <td className="px-4 py-3">
                      <Link href={`/leads/${lead.id}`} className="font-semibold no-underline">
                        {lead.full_name}
                      </Link>
                      <div className="text-xs text-[#5A6075]">
                        {lead.company ?? "No company given"}
                      </div>
                      {lead.do_not_contact && (
                        <div className="mt-1 text-xs font-semibold text-[#8A3B00]">
                          Do not contact
                        </div>
                      )}
                    </td>
                    <td className="max-w-[300px] px-4 py-3 text-[#3A4057]">
                      {lead.latest_message || <span className="text-[#5A6075]">—</span>}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {lead.score === null ? (
                        <span className="text-[#5A6075]">—</span>
                      ) : (
                        <>
                          <strong>{lead.score}</strong>
                          {lead.score_source === "fake" && (
                            <span className="ml-1.5 text-xs text-[#5A6075]">(fake AI)</span>
                          )}
                        </>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-start gap-1">
                        <PriorityBadge priority={lead.priority} />
                        <AiStatusPill status={lead.ai_status} />
                      </div>
                    </td>
                    <td className="px-4 py-3">{lead.stage.label ?? "—"}</td>
                    <td className="px-4 py-3 text-[#3A4057]">
                      {lead.assigned_to?.name ?? <span className="text-[#5A6075]">Unassigned</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-[#5A6075]">
                      {timeAgo(lead.last_interaction_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E3E6EF] px-4 py-3 text-sm">
            <span className="text-[#5A6075]">
              Page {data.page} of {pages}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                className={buttonSecondary}
                disabled={data.page <= 1}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
              >
                Previous
              </button>
              <button
                type="button"
                className={buttonSecondary}
                disabled={data.page >= pages}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      )}

      {adding && <NewLeadDialog onClose={() => setAdding(false)} onCreated={load} />}
    </div>
  );
}

const NEW_LEAD_FIELDS: { name: string; label: string; type: string; required: boolean }[] = [
  { name: "full_name", label: "Name", type: "text", required: true },
  { name: "email", label: "Email", type: "email", required: false },
  { name: "phone", label: "Phone", type: "tel", required: false },
  { name: "company", label: "Company", type: "text", required: false },
];

function NewLeadDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const router = useRouter();
  const ref = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [merged, setMerged] = useState<string | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    // Safety net: React runs this cleanup when the page is hidden or unmounted, so the modal can
    // never stay open (and keep the rest of the app inert) after any kind of navigation.
    return () => dialog?.close();
  }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => String(fd.get(k) ?? "").trim() || undefined;
    setBusy(true);
    setError(null);
    try {
      const lead = await api.createLead({
        full_name: v("full_name") ?? "",
        email: v("email"),
        phone: v("phone"),
        company: v("company"),
        message: v("message"),
      });
      onCreated();
      if (lead.merged) {
        setMerged(lead.id);
      } else {
        // Close the modal first: Next keeps this page mounted (hidden), and an open modal would
        // leave the whole next page inert (unclickable).
        ref.current?.close();
        router.push(`/leads/${lead.id}`);
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="new-lead-title"
      className="m-auto w-full max-w-lg rounded-xl border border-[#E3E6EF] p-0 backdrop:bg-black/40"
    >
      <form onSubmit={submit} className="flex flex-col gap-4 p-6">
        <h2 id="new-lead-title" className="text-lg font-bold">
          New lead
        </h2>
        {error && (
          <p role="alert" className="rounded-lg bg-[#FEF6F3] px-3 py-2 text-sm text-[#A32A12]">
            {error}
          </p>
        )}
        {merged ? (
          <p role="status" className="rounded-lg bg-[#EEF7F1] px-3 py-2 text-sm text-[#1E5E3A]">
            This person is already a lead (same email or phone), so the details were added to the
            existing lead.{" "}
            <Link href={`/leads/${merged}`} onClick={() => ref.current?.close()}>
              Open it
            </Link>
          </p>
        ) : (
          <>
            {NEW_LEAD_FIELDS.map((f) => (
              <div key={f.name} className="flex flex-col gap-1.5">
                <label htmlFor={`nl-${f.name}`} className="text-[13px] font-semibold">
                  {f.label}{" "}
                  <span className="font-normal text-[#5A6075]">
                    {f.required ? "(required)" : "(optional)"}
                  </span>
                </label>
                <input
                  id={`nl-${f.name}`}
                  name={f.name}
                  type={f.type}
                  required={f.required}
                  className={field}
                />
              </div>
            ))}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="nl-message" className="text-[13px] font-semibold">
                Their message{" "}
                <span className="font-normal text-[#5A6075]">(optional; it will be scored)</span>
              </label>
              <textarea id="nl-message" name="message" rows={3} className={`${field} py-2`} />
            </div>
          </>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className={buttonSecondary} onClick={() => ref.current?.close()}>
            {merged ? "Close" : "Cancel"}
          </button>
          {!merged && (
            <button type="submit" disabled={busy} className={buttonPrimary}>
              {busy ? "Saving…" : "Add lead"}
            </button>
          )}
        </div>
      </form>
    </dialog>
  );
}
