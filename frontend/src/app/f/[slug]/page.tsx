import type { Metadata } from "next";
import { Suspense } from "react";

import { DemoBanner } from "@/components/demo-banner";

import { FormSkeleton, PublicForm } from "./public-form";

export const metadata: Metadata = { title: "Contact us" };

// The slug is only known at request time; with Cache Components, a client component that reads
// it via useParams must sit inside Suspense (Next.js 16 docs: use-params).
export default function PublicFormPage() {
  return (
    <div className="flex min-h-full flex-1 flex-col bg-[#F6F7FB] font-[family-name:var(--font-public-sans)] text-[#1A1D2B]">
      <DemoBanner text="Fictional business. Submissions go to a local test inbox only." />
      <main className="flex-1 px-4 pt-10 pb-12">
        <div className="mx-auto max-w-[640px]">
          <Suspense fallback={<FormSkeleton />}>
            <PublicForm />
          </Suspense>
          <p className="mt-5 text-center text-xs text-[#5A6075]">Powered by Replyline</p>
        </div>
      </main>
    </div>
  );
}
