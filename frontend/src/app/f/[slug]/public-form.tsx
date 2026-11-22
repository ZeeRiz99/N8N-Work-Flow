"use client";

import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { api, ApiError, type FormConfig } from "@/lib/api";

type FieldErrors = Record<string, string>;

const inputCls =
  "w-full min-h-11 rounded-lg border border-[#CDD2E0] bg-white px-3 text-[#1A1D2B] aria-[invalid=true]:border-[#A32A12]";

function Field({
  id,
  label,
  required,
  error,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 basis-60 flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}{" "}
        <span className="font-normal text-[#5A6075]">{required ? "(required)" : "(optional)"}</span>
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-[13px] text-[#A32A12]">
          {error}
        </p>
      )}
    </div>
  );
}

export function PublicForm() {
  const { slug } = useParams<{ slug: string }>();
  const [config, setConfig] = useState<FormConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [reference, setReference] = useState<string | null>(null);

  useEffect(() => {
    api
      .formConfig(slug)
      .then(setConfig)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "The form could not load."));
  }, [slug]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config || sending) return;
    const fd = new FormData(event.currentTarget);
    const text = (k: string) => {
      const v = String(fd.get(k) ?? "").trim();
      return v === "" ? undefined : v;
    };
    const body = {
      full_name: text("full_name"),
      email: text("email"),
      phone: text("phone"),
      company: text("company"),
      service: text("service"),
      budget: text("budget"),
      timeline: text("timeline"),
      message: text("message"),
      consent: fd.get("consent") === "on",
      nickname: text("nickname"),
    };
    setSending(true);
    setErrors({});
    setFormError(null);
    try {
      const res = await api.submitLead(config.form_key, body);
      setReference(res.reference);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && e.body?.error.details) {
        setErrors(Object.fromEntries(e.body.error.details.map((d) => [d.field, d.message])));
        setFormError("Please check the highlighted fields.");
      } else if (e instanceof ApiError && e.status === 429) {
        setFormError("Too many requests. Please wait a minute and try again.");
      } else {
        setFormError("Something went wrong. Please try again in a moment.");
      }
    } finally {
      setSending(false);
    }
  }

  if (loadError) {
    return (
      <p role="alert" className="rounded-xl border border-[#F2C2B5] bg-[#FEF6F3] p-5">
        {loadError}
      </p>
    );
  }
  if (!config) return <FormSkeleton />;

  if (reference) {
    return (
      <div role="status" className="rounded-xl border border-[#E3E6EF] bg-white p-7">
        <h2 className="text-xl font-bold">Thanks, we have your request</h2>
        <p className="mt-2 text-[#3A4057]">{config.response_time_line}</p>
        <p className="mt-3 text-xs text-[#5A6075]">Reference: {reference}</p>
      </div>
    );
  }

  const err = (k: string) => errors[k];
  const invalid = (k: string) => (errors[k] ? true : undefined);
  const describedBy = (k: string) => (errors[k] ? `${k}-error` : undefined);

  return (
    <>
      <div className="mb-5 flex flex-col gap-1.5">
        <h1 className="text-[28px] leading-tight font-bold tracking-tight">
          Tell us about your project
        </h1>
        <p className="max-w-[56ch] text-[#3A4057]">
          Share a few details and we will reply by email. {config.response_time_line}
        </p>
      </div>
      <form
        onSubmit={onSubmit}
        noValidate
        className="flex flex-col gap-5 rounded-xl border border-[#E3E6EF] bg-white p-7"
      >
        {formError && (
          <p role="alert" className="rounded-lg bg-[#FEF6F3] px-3 py-2 text-sm text-[#A32A12]">
            {formError}
          </p>
        )}
        <div className="flex flex-wrap gap-5">
          <Field id="full_name" label="Full name" required error={err("full_name")}>
            <input
              id="full_name"
              name="full_name"
              autoComplete="name"
              required
              className={inputCls}
              aria-invalid={invalid("full_name")}
              aria-describedby={describedBy("full_name")}
            />
          </Field>
          <Field id="email" label="Email" required error={err("email")}>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              className={inputCls}
              aria-invalid={invalid("email")}
              aria-describedby={describedBy("email")}
            />
          </Field>
        </div>
        <div className="flex flex-wrap gap-5">
          <Field id="phone" label="Phone" error={err("phone")}>
            <input
              id="phone"
              name="phone"
              type="tel"
              autoComplete="tel"
              placeholder="Include the country code"
              className={inputCls}
            />
          </Field>
          <Field id="company" label="Company" error={err("company")}>
            <input id="company" name="company" autoComplete="organization" className={inputCls} />
          </Field>
        </div>
        <Field id="service" label="What do you need?" error={err("service")}>
          <select id="service" name="service" className={inputCls} defaultValue="">
            <option value="">Choose a service</option>
            {config.services.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
        <div className="flex flex-wrap gap-5">
          <Field id="budget" label="Budget in USD" error={err("budget")}>
            <select id="budget" name="budget" className={inputCls} defaultValue="">
              <option value="">Not sure yet</option>
              {config.budget_options.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </Field>
          <Field id="timeline" label="When do you need it?" error={err("timeline")}>
            <select id="timeline" name="timeline" className={inputCls} defaultValue="">
              <option value="">No preference</option>
              {config.timeline_options.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
        </div>
        <Field id="message" label="Your message" required error={err("message")}>
          <textarea
            id="message"
            name="message"
            rows={5}
            maxLength={4000}
            required
            className={`${inputCls} py-3`}
            aria-invalid={invalid("message")}
            aria-describedby={describedBy("message")}
          />
        </Field>
        {/* Honeypot: hidden from people and screen readers; bots tend to fill it in. */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
          <label htmlFor="nickname">Leave this field empty</label>
          <input id="nickname" name="nickname" tabIndex={-1} autoComplete="off" />
        </div>
        <div className="flex items-start gap-2.5">
          <input
            id="consent"
            name="consent"
            type="checkbox"
            className="mt-0.5 h-5 w-5 shrink-0 accent-[#4338CA]"
            aria-invalid={invalid("consent")}
            aria-describedby={describedBy("consent")}
          />
          <div>
            <label htmlFor="consent" className="text-[13px] text-[#3A4057]">
              I agree that {config.organization_name} may store these details and contact me about
              this request.
            </label>
            {err("consent") && (
              <p id="consent-error" className="text-[13px] text-[#A32A12]">
                {err("consent")}
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={sending}
            className="min-h-12 rounded-lg bg-[#4338CA] px-6 text-[15px] font-semibold text-white disabled:opacity-60"
          >
            {sending ? "Sending…" : "Send request"}
          </button>
          <span className="text-xs text-[#5A6075]">
            We use your details only to answer this request.
          </span>
        </div>
      </form>
    </>
  );
}

export function FormSkeleton() {
  return (
    <div aria-busy="true" className="space-y-3">
      <div className="h-9 w-2/3 animate-pulse rounded bg-[#E9ECF4]" />
      <div className="h-96 animate-pulse rounded-xl bg-[#E9ECF4]" />
    </div>
  );
}
