"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonPrimary, buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, errorText, type Stage } from "@/lib/api";

export default function PipelineSettingsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [stages, setStages] = useState<Stage[]>([]);
  const [label, setLabel] = useState("");
  const [category, setCategory] = useState("open");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStages(await api.stages());
    } catch (e) {
      setMessage(errorText(e));
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(fn: () => Promise<unknown>, done: string) {
    setMessage(null);
    try {
      await fn();
      setMessage(done);
      await load();
    } catch (e) {
      setMessage(errorText(e));
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    await run(() => api.addStage(label.trim(), category), "Stage added.");
    setLabel("");
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">Pipeline</h1>
        <p className="text-[#5A6075]">
          The stages a lead moves through. Built-in stages can be renamed and reordered but not
          removed, because automation relies on them.
        </p>
      </header>
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}
      <ol className={`${card} flex flex-col overflow-hidden`}>
        {stages.map((s, i) => (
          <li
            key={s.id}
            className="flex flex-wrap items-center gap-3 border-b border-[#EEF0F6] p-3 last:border-b-0"
          >
            <span className="w-6 text-right text-sm text-[#5A6075] tabular-nums">{i + 1}</span>
            <label htmlFor={`stage-${s.id}`} className="sr-only">
              Name of stage {i + 1}
            </label>
            <input
              id={`stage-${s.id}`}
              className={`${field} max-w-xs flex-1`}
              defaultValue={s.label}
              maxLength={60}
              disabled={!isAdmin}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== s.label) run(() => api.updateStage(s.id, { label: v }), "Renamed.");
              }}
            />
            <span className="rounded-full bg-[#F3F4FA] px-2 text-xs text-[#444B63] capitalize">
              {s.category}
            </span>
            {isAdmin && (
              <div className="ml-auto flex gap-1">
                <button
                  type="button"
                  aria-label={`Move ${s.label} up`}
                  className={buttonSecondary}
                  disabled={i === 0}
                  onClick={() => run(() => api.updateStage(s.id, { position: i - 1 }), "Moved.")}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Move ${s.label} down`}
                  className={buttonSecondary}
                  disabled={i === stages.length - 1}
                  onClick={() => run(() => api.updateStage(s.id, { position: i + 1 }), "Moved.")}
                >
                  ↓
                </button>
                {!s.is_system && (
                  <button
                    type="button"
                    className={buttonSecondary}
                    onClick={() => run(() => api.deleteStage(s.id), "Stage removed.")}
                  >
                    Remove
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
      {isAdmin && (
        <form onSubmit={add} className={`${card} flex flex-wrap items-end gap-3 p-5`}>
          <div className="flex min-w-[220px] flex-1 flex-col gap-1">
            <label htmlFor="new-stage" className="text-xs font-semibold text-[#3A4057]">
              New stage
            </label>
            <input
              id="new-stage"
              className={field}
              required
              maxLength={60}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="new-cat" className="text-xs font-semibold text-[#3A4057]">
              Kind
            </label>
            <select
              id="new-cat"
              className={field}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="open">Open (still in progress)</option>
              <option value="won">Won</option>
              <option value="lost">Lost</option>
            </select>
          </div>
          <button type="submit" className={buttonPrimary}>
            Add stage
          </button>
        </form>
      )}
    </div>
  );
}
