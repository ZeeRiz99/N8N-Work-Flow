"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { UserMenu } from "@/components/session";

// Sidebar from docs/design (master prompt §10.3). Screens not built yet are labelled "Soon"
// instead of linking to an empty page (every control works or says it is coming).
const NAV: { label: string; href?: string; icon: ReactNode }[] = [
  { label: "Overview", icon: <path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z" /> },
  {
    label: "Leads",
    href: "/leads",
    icon: (
      <>
        <circle cx="9" cy="8" r="3.5" />
        <path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.4c2.2.7 3.5 2.6 3.5 5.6" />
      </>
    ),
  },
  {
    label: "Approvals",
    href: "/approvals",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="m8 12.5 2.8 2.8L16 9.5" />
      </>
    ),
  },
  {
    label: "Duplicates",
    href: "/duplicates",
    icon: <path d="M8 8h11v11H8zM5 16V5h11" />,
  },
  {
    label: "Follow-ups",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
  },
  { label: "AI Assistant", href: "/assistant", icon: <path d="M4 5h16v11H9l-5 4z" /> },
  {
    label: "Automation",
    href: "/automation",
    icon: (
      <>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="6" cy="18" r="2.5" />
        <circle cx="18" cy="12" r="2.5" />
        <path d="M6 8.5v7M8.5 6H12a4 4 0 0 1 4 4M8.5 18H12a4 4 0 0 0 4-4" />
      </>
    ),
  },
  { label: "Analytics", icon: <path d="M5 20v-9M12 20V5M19 20v-6" /> },
  {
    label: "Integrations",
    href: "/integrations",
    icon: <path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5" />,
  },
  {
    label: "Settings",
    href: "/settings",
    icon: <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />,
  },
];

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex flex-1 flex-wrap items-stretch bg-[#F6F7FB]">
      <aside className="flex w-full flex-col gap-6 border-[#E3E6EF] bg-white px-4 py-5 md:w-[232px] md:flex-none md:border-r">
        <div className="flex items-center gap-2.5 px-1">
          <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="#4338CA" />
            <path
              d="M13 9.5 8 14.5l5 5M8 14.5h9.5a5.5 5.5 0 0 1 5.5 5.5v2"
              fill="none"
              stroke="#FFFFFF"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="text-[17px] font-bold tracking-tight">Replyline</span>
        </div>
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          {NAV.map((item) => {
            const active = item.href && pathname.startsWith(item.href);
            const cls =
              "flex min-h-11 items-center gap-2.5 rounded-lg px-3 font-medium no-underline";
            if (!item.href) {
              return (
                <span
                  key={item.label}
                  aria-disabled="true"
                  className={`${cls} cursor-default text-[#5A6075]`}
                >
                  <Icon>{item.icon}</Icon>
                  <span className="flex-1">{item.label}</span>
                  <span className="rounded-full bg-[#F3F4FA] px-2 text-[11px] font-semibold text-[#5A6075]">
                    Soon
                  </span>
                </span>
              );
            }
            return (
              <Link
                key={item.label}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`${cls} ${active ? "bg-[#EEF0FF] font-semibold text-[#3730A3]" : "text-[#3A4057] hover:bg-[#F6F7FB]"}`}
              >
                <Icon>{item.icon}</Icon>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex gap-2 rounded-[10px] bg-[#F3F4FA] p-3 text-xs text-[#444B63]">
          <span>Drafts only. Nothing is sent without your approval.</span>
        </div>
      </aside>
      <div className="min-w-0 flex-[999_1_560px]">
        <div className="flex flex-wrap items-center justify-end gap-3 border-b border-[#E3E6EF] bg-white px-4 py-3 sm:px-8">
          <UserMenu />
        </div>
        <main className="mx-auto w-full max-w-[1180px] px-4 py-7 sm:px-8">{children}</main>
      </div>
    </div>
  );
}
