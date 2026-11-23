"use client";

import { useEffect, useState } from "react";

import { buttonPrimary, buttonSecondary } from "@/components/ui-tokens";
import { api, errorText } from "@/lib/api";

/** Development helper: load or remove fictional sample leads (admins only). */
export function useSampleData(enabled: boolean) {
  const [status, setStatus] = useState<{ available: boolean; sample_leads: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    api
      .sampleStatus()
      .then(setStatus)
      .catch(() => undefined);
  }, [enabled]);

  async function run(fn: () => Promise<string>, after: () => void) {
    setBusy(true);
    setMessage(null);
    try {
      setMessage(await fn());
      setStatus(await api.sampleStatus());
      after();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return {
    visible: enabled && !!status?.available,
    count: status?.sample_leads ?? 0,
    busy,
    message,
    load: (after: () => void) =>
      run(async () => {
        const r = await api.loadSample(40);
        return `Added ${r.leads} fictional leads (scored by the offline AI) and ${r.duplicate_pairs} duplicate pairs to review.`;
      }, after),
    clear: (after: () => void) =>
      run(async () => {
        const r = await api.clearSample();
        return `Removed ${r.removed} sample leads. Your own leads were not touched.`;
      }, after),
  };
}

export function LoadSampleButton({
  sample,
  onDone,
}: {
  sample: ReturnType<typeof useSampleData>;
  onDone: () => void;
}) {
  if (!sample.visible) return null;
  return (
    <div className="mt-4 flex flex-col items-center gap-2">
      <button
        type="button"
        className={buttonPrimary}
        disabled={sample.busy}
        onClick={() => sample.load(onDone)}
      >
        {sample.busy ? "Loading sample data…" : "Load 40 sample leads"}
      </button>
      <p className="text-xs text-[#5A6075]">
        Fictional people and companies, for testing. You can remove them in one click.
      </p>
    </div>
  );
}

export function RemoveSampleButton({
  sample,
  onDone,
}: {
  sample: ReturnType<typeof useSampleData>;
  onDone: () => void;
}) {
  if (!sample.visible || sample.count === 0) return null;
  return (
    <button
      type="button"
      className={buttonSecondary}
      disabled={sample.busy}
      onClick={() => {
        if (window.confirm(`Remove all ${sample.count} sample leads? Your own leads stay.`)) {
          sample.clear(onDone);
        }
      }}
    >
      {sample.busy ? "Working…" : `Remove sample data (${sample.count})`}
    </button>
  );
}
