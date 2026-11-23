"use client";

import { useParams, useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { buttonPrimary, card, field } from "@/components/ui-tokens";
import { api, ApiError, errorText } from "@/lib/api";

export function AcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [info, setInfo] = useState<{
    organization_name: string;
    email: string;
    role: string;
    has_account: boolean;
  } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .invitationInfo(token)
      .then(setInfo)
      .catch((e) => setProblem(e instanceof ApiError ? e.message : errorText(e)));
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await api.acceptInvite(token, name, password);
      router.replace("/leads");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : errorText(err));
      setBusy(false);
    }
  }

  if (problem && !info) {
    return (
      <div role="alert" className={`${card} p-6 text-center`}>
        <p className="font-semibold">{problem}</p>
      </div>
    );
  }
  if (!info) return <div aria-busy="true" className="h-72 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  return (
    <form onSubmit={submit} className={`${card} flex flex-col gap-4 p-6`}>
      <p className="text-sm">
        You are invited to <strong>{info.organization_name}</strong> as{" "}
        <strong className="capitalize">{info.role}</strong>, with the email{" "}
        <strong>{info.email}</strong>.
      </p>
      {!info.has_account && (
        <div className="flex flex-col gap-1">
          <label htmlFor="inv-name" className="text-[13px] font-semibold">
            Your name
          </label>
          <input
            id="inv-name"
            className={field}
            required
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
      )}
      <div className="flex flex-col gap-1">
        <label htmlFor="inv-pw" className="text-[13px] font-semibold">
          {info.has_account ? "Your existing password" : "Choose a password"}
        </label>
        <input
          id="inv-pw"
          type="password"
          required
          autoComplete={info.has_account ? "current-password" : "new-password"}
          className={field}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-describedby="inv-pw-help"
        />
        <p id="inv-pw-help" className="text-xs text-[#5A6075]">
          {info.has_account
            ? "You already have a Replyline account with this email."
            : "At least 10 characters, not a common password."}
        </p>
      </div>
      {problem && (
        <p role="alert" className="text-sm text-[#A32A12]">
          {problem}
        </p>
      )}
      <button type="submit" className={buttonPrimary} disabled={busy}>
        {busy ? "Joining…" : "Join the team"}
      </button>
    </form>
  );
}
