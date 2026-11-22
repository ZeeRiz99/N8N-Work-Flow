"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

import { api, AuthRequired, type Me } from "@/lib/api";

const SessionContext = createContext<Me | null>(null);

export function useSession(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useSession must be used inside <RequireSession>");
  return me;
}

/** Renders children only for a logged-in user; otherwise sends them to /login and back. */
export function RequireSession({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((m) => !cancelled && setMe(m))
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof AuthRequired) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        } else {
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router, pathname]);

  if (failed) {
    return (
      <p role="alert" className="m-8 rounded-xl border border-[#F2C2B5] bg-[#FEF6F3] p-5">
        The backend is not reachable. Is it running on port 8000?
      </p>
    );
  }
  if (!me) {
    return <div aria-busy="true" className="m-8 h-24 animate-pulse rounded-xl bg-[#E9ECF4]" />;
  }
  return <SessionContext.Provider value={me}>{children}</SessionContext.Provider>;
}

export function UserMenu() {
  const me = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm text-[#3A4057]">
        <strong className="font-semibold text-[#1A1D2B]">{me.full_name}</strong> ·{" "}
        {me.organization_name} · {me.role}
      </span>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await api.logout().catch(() => undefined);
          router.replace("/login");
        }}
        className="min-h-11 rounded-lg border border-[#CDD2E0] bg-white px-4 font-medium disabled:opacity-60"
      >
        Log out
      </button>
    </div>
  );
}
