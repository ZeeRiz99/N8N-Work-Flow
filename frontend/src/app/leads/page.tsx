import Link from "next/link";
import type { Metadata } from "next";

import { DemoBanner } from "@/components/demo-banner";
import { RequireSession, UserMenu } from "@/components/session";

import { LeadsTable } from "./leads-table";

export const metadata: Metadata = { title: "Leads · Replyline" };

export default function LeadsPage() {
  return (
    <div className="flex min-h-full flex-1 flex-col bg-[#F6F7FB] font-[family-name:var(--font-public-sans)] text-[#1A1D2B]">
      <DemoBanner text="Fictional people and companies. Scores come from a fake AI until Phase 5." />
      <RequireSession>
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 py-7 sm:px-8">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[#E3E6EF] pb-4">
            <span className="text-lg font-bold tracking-tight">Replyline</span>
            <UserMenu />
          </div>
          <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-[26px] leading-tight font-bold tracking-tight">Leads</h1>
              <p className="mt-1 text-[#5A6075]">Every row comes from the database.</p>
            </div>
            <Link
              href="/f/harbor-web"
              className="inline-flex min-h-11 items-center rounded-lg border border-[#CDD2E0] bg-white px-4 font-medium"
            >
              Open public lead form
            </Link>
          </header>
          <LeadsTable />
        </main>
      </RequireSession>
    </div>
  );
}
