import type { Metadata } from "next";
import { Suspense } from "react";

import { LeadDetail } from "./lead-detail";

export const metadata: Metadata = { title: "Lead · Replyline" };

// The id is only known at request time; useParams inside Suspense (Next.js 16, Cache Components).
export default function LeadPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-xl bg-[#E9ECF4]" />}>
      <LeadDetail />
    </Suspense>
  );
}
