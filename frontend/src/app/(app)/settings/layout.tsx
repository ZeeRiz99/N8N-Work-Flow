"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, Suspense } from "react";

const TABS = [
  ["/settings/scoring", "Lead scoring"],
  ["/settings/ai", "AI"],
] as const;

function Tabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Settings sections" className="flex gap-2 border-b border-[#E3E6EF]">
      {TABS.map(([href, label]) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold no-underline ${active ? "border-[#4338CA] text-[#3730A3]" : "border-transparent text-[#5A6075] hover:text-[#1A1D2B]"}`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <Suspense fallback={<div className="h-10" />}>
        <Tabs />
      </Suspense>
      {children}
    </div>
  );
}
