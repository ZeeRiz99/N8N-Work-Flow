import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "../auth-form";

export const metadata: Metadata = { title: "Create account · Replyline" };

export default function RegisterPage() {
  return (
    <>
      <h1 className="mb-1 text-center text-2xl font-bold tracking-tight">Create your account</h1>
      <p className="mb-4 text-center text-sm text-[#5A6075]">
        Sign-up is open in development only.
      </p>
      <Suspense fallback={<div className="h-96 animate-pulse rounded-xl bg-[#E9ECF4]" />}>
        <AuthForm mode="register" />
      </Suspense>
    </>
  );
}
