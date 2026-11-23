import { type ReactNode, Suspense } from "react";

import { AppShell } from "@/components/app-shell";
import { DemoBanner } from "@/components/demo-banner";
import { RequireSession } from "@/components/session";

// RequireSession reads the current path (usePathname). On dynamic routes such as /leads/[id]
// that is only known at request time, so with Cache Components it must sit inside Suspense.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col font-[family-name:var(--font-public-sans)] text-[#1A1D2B]">
      <DemoBanner text="Fictional people and companies. Scores come from a fake AI until Phase 5." />
      <Suspense
        fallback={
          <div aria-busy="true" className="m-8 h-24 animate-pulse rounded-xl bg-[#E9ECF4]" />
        }
      >
        <RequireSession>
          <AppShell>{children}</AppShell>
        </RequireSession>
      </Suspense>
    </div>
  );
}
