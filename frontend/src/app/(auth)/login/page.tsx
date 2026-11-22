import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "../auth-form";

export const metadata: Metadata = { title: "Log in · Replyline" };

// AuthForm reads ?next= with useSearchParams, which needs Suspense under Cache Components.
export default function LoginPage() {
  return (
    <>
      <h1 className="mb-4 text-center text-2xl font-bold tracking-tight">Log in</h1>
      <Suspense fallback={<div className="h-72 animate-pulse rounded-xl bg-[#E9ECF4]" />}>
        <AuthForm mode="login" />
      </Suspense>
    </>
  );
}
