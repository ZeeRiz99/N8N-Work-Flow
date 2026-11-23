"use client";

import Link from "next/link";
import { type ChangeEvent, useState } from "react";

import { buttonPrimary, buttonSecondary, card } from "@/components/ui-tokens";
import { api, errorText, type ImportReport } from "@/lib/api";

const MAX_BYTES = 2 * 1024 * 1024;
const LABELS: Record<string, string> = {
  full_name: "Name",
  email: "Email",
  phone: "Phone",
  company: "Company",
  website: "Website",
  message: "Message",
};

export default function ImportPage() {
  const [csv, setCsv] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<ImportReport | null>(null);
  const [result, setResult] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    setPreview(null);
    setResult(null);
    setError(null);
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError("The file is larger than 2 MB. Split it and import the parts.");
      return;
    }
    if (!/\.csv$/i.test(file.name)) {
      setError("Choose a .csv file (in Excel: File → Save As → CSV UTF-8).");
      return;
    }
    const text = await file.text();
    setCsv(text);
    setFileName(file.name);
    setBusy(true);
    try {
      setPreview(await api.importCsv(text, true));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!csv || !preview) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.importCsv(csv, false, preview.mapping));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <nav aria-label="Breadcrumb" className="text-[13px] text-[#5A6075]">
        <Link href="/leads" className="no-underline">
          Leads
        </Link>{" "}
        / Import CSV
      </nav>
      <h1 className="text-[26px] leading-tight font-bold tracking-tight">Import leads from CSV</h1>
      <p className="text-[#3A4057]">
        The first row must hold column names such as Name, Email, Phone, Company and Notes. You see
        a preview before anything is saved. People already in Replyline (same email or phone) are
        updated, not duplicated. Up to 5,000 rows and 2 MB.
      </p>

      <section className={`${card} flex flex-col gap-3 p-6`}>
        <label htmlFor="csv-file" className="text-[13px] font-semibold">
          CSV file
        </label>
        <input
          id="csv-file"
          type="file"
          accept=".csv,text/csv"
          onChange={onFile}
          className="text-sm file:mr-3 file:min-h-11 file:rounded-lg file:border file:border-[#CDD2E0] file:bg-white file:px-4 file:font-medium"
        />
        {busy && <p aria-live="polite">Checking the file…</p>}
        {error && (
          <p role="alert" className="rounded-lg bg-[#FEF6F3] px-3 py-2 text-sm text-[#A32A12]">
            {error}
          </p>
        )}
      </section>

      {preview && !result && (
        <section className={`${card} flex flex-col gap-4 p-6`} aria-label="Preview">
          <h2 className="text-base font-semibold">Preview of {fileName}</h2>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Rows", preview.total_rows],
              ["New leads", preview.would_create],
              ["Updates", preview.would_merge],
              ["Rows with problems", preview.error_count],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-[#F6F7FB] p-3">
                <dt className="text-xs text-[#5A6075]">{k}</dt>
                <dd className="text-2xl font-bold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <div>
            <h3 className="text-[13px] font-semibold">Columns used</h3>
            <ul className="mt-1 flex flex-wrap gap-2 text-sm">
              {Object.entries(preview.mapping).map(([target, col]) => (
                <li key={target} className="rounded-full bg-[#EEF0FF] px-3 py-1 text-[#2A2480]">
                  {LABELS[target] ?? target} ← “{col}”
                </li>
              ))}
            </ul>
          </div>
          {preview.errors.length > 0 && (
            <div>
              <h3 className="text-[13px] font-semibold">These rows will be skipped</h3>
              <table className="mt-1 w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-[#5A6075]">
                    <th scope="col" className="py-1">
                      Row
                    </th>
                    <th scope="col">Field</th>
                    <th scope="col">Problem</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.errors.map((e, i) => (
                    <tr key={i} className="border-t border-[#EEF0F6]">
                      <td className="py-1.5 tabular-nums">{e.row}</td>
                      <td>{LABELS[e.field] ?? e.field}</td>
                      <td>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={buttonPrimary}
              disabled={busy || preview.valid_rows === 0}
              onClick={confirm}
            >
              Import {preview.valid_rows} {preview.valid_rows === 1 ? "row" : "rows"}
            </button>
            <Link href="/leads" className={buttonSecondary}>
              Cancel
            </Link>
          </div>
        </section>
      )}

      {result && (
        <section role="status" className={`${card} flex flex-col gap-3 p-6`}>
          <h2 className="text-base font-semibold">Import finished</h2>
          <p>
            {result.created} new {result.created === 1 ? "lead" : "leads"}, {result.merged} updated,{" "}
            {result.error_count} skipped.
          </p>
          <div>
            <Link href="/leads" className={buttonPrimary}>
              View leads
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
