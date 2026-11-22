"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import { api, ApiError } from "@/lib/api";

const inputCls =
  "w-full min-h-11 rounded-lg border border-[#CDD2E0] bg-white px-3 text-[#1A1D2B] aria-[invalid=true]:border-[#A32A12]";

/** Only same-site paths are allowed as a post-login destination (no open redirects). */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/leads";
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const fd = new FormData(event.currentTarget);
    const v = (k: string) => String(fd.get(k) ?? "").trim();
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      if (mode === "login") {
        await api.login(v("email"), String(fd.get("password") ?? ""));
      } else {
        await api.register({
          organization_name: v("organization_name"),
          full_name: v("full_name"),
          email: v("email"),
          password: String(fd.get("password") ?? ""),
        });
      }
      router.replace(safeNext(params.get("next")));
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && e.body?.error.details) {
        setFieldErrors(Object.fromEntries(e.body.error.details.map((d) => [d.field, d.message])));
        setError("Please check the highlighted fields.");
      } else if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError("The server is not reachable. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  const field = (
    id: string,
    label: string,
    type = "text",
    autoComplete?: string,
    hint?: string,
  ) => (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        autoComplete={autoComplete}
        required
        className={inputCls}
        aria-invalid={fieldErrors[id] ? true : undefined}
        aria-describedby={fieldErrors[id] ? `${id}-error` : hint ? `${id}-hint` : undefined}
      />
      {hint && !fieldErrors[id] && (
        <p id={`${id}-hint`} className="text-xs text-[#5A6075]">
          {hint}
        </p>
      )}
      {fieldErrors[id] && (
        <p id={`${id}-error`} className="text-[13px] text-[#A32A12]">
          {fieldErrors[id]}
        </p>
      )}
    </div>
  );

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4 rounded-xl border border-[#E3E6EF] bg-white p-7"
    >
      {error && (
        <p role="alert" className="rounded-lg bg-[#FEF6F3] px-3 py-2 text-sm text-[#A32A12]">
          {error}
        </p>
      )}
      {mode === "register" && field("organization_name", "Business name", "text", "organization")}
      {mode === "register" && field("full_name", "Your name", "text", "name")}
      {field("email", "Email", "email", "email")}
      {field(
        "password",
        "Password",
        "password",
        mode === "login" ? "current-password" : "new-password",
        mode === "register"
          ? "At least 10 characters, upper and lower case, and a number."
          : undefined,
      )}
      <button
        type="submit"
        disabled={busy}
        className="min-h-12 rounded-lg bg-[#4338CA] px-6 text-[15px] font-semibold text-white disabled:opacity-60"
      >
        {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
      </button>
      <p className="text-center text-sm text-[#3A4057]">
        {mode === "login" ? (
          <>
            New here? <Link href="/register">Create an account</Link>
          </>
        ) : (
          <>
            Already have an account? <Link href="/login">Log in</Link>
          </>
        )}
      </p>
    </form>
  );
}
