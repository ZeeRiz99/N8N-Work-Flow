import type { Metadata } from "next";
import { Suspense } from "react";

import { AcceptInvite } from "./accept-invite";

export const metadata: Metadata = { title: "Join your team · Replyline" };

export default function InvitePage() {
  return (
    <>
      <h1 className="mb-4 text-center text-2xl font-bold tracking-tight">Join your team</h1>
      <Suspense fallback={<div className="h-72 animate-pulse rounded-xl bg-[#E9ECF4]" />}>
        <AcceptInvite />
      </Suspense>
    </>
  );
}
