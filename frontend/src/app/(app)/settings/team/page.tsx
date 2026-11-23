"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/session";
import { buttonDanger, buttonPrimary, buttonSecondary, card, field } from "@/components/ui-tokens";
import { api, errorText, type Invitation, type Member } from "@/lib/api";

export default function TeamSettingsPage() {
  const me = useSession();
  const isAdmin = me.role === "owner" || me.role === "admin";
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [created, setCreated] = useState<Invitation | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMembers(await api.members());
      if (isAdmin) setInvites(await api.invitations());
    } catch (e) {
      setMessage(errorText(e));
    }
  }, [isAdmin]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(fn: () => Promise<unknown>, done: string) {
    setMessage(null);
    try {
      await fn();
      setMessage(done);
      await load();
    } catch (e) {
      setMessage(errorText(e));
    }
  }

  async function invite(e: FormEvent) {
    e.preventDefault();
    try {
      const inv = await api.invite(email.trim(), role);
      setCreated(inv);
      setEmail("");
      setMessage(
        inv.emailed
          ? `Invitation emailed to ${inv.email}.`
          : "Invitation created. Copy the link below.",
      );
      await load();
    } catch (err) {
      setMessage(errorText(err));
    }
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <header>
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">Team</h1>
        <p className="text-[#5A6075]">
          Owners manage everything, admins manage settings and the team, members work leads and
          approve drafts.
        </p>
      </header>
      {message && (
        <p role="status" className="text-sm text-[#3A4057]">
          {message}
        </p>
      )}

      <section className={`${card} overflow-x-auto`}>
        <table className="w-full min-w-[560px] text-sm">
          <caption className="px-5 pt-5 pb-3 text-left font-semibold">Members</caption>
          <thead>
            <tr className="border-y border-[#E3E6EF] bg-[#FAFBFD] text-left text-xs text-[#5A6075]">
              <th className="px-5 py-2 font-semibold">Name</th>
              <th className="px-3 py-2 font-semibold">Role</th>
              <th className="px-3 py-2 font-semibold">Last login</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className="border-b border-[#EEF0F6] last:border-b-0">
                <td className="px-5 py-2.5">
                  <div className="font-medium">{m.full_name}</div>
                  <div className="text-xs text-[#5A6075]">{m.email}</div>
                </td>
                <td className="px-3 py-2.5">
                  {isAdmin && m.user_id !== me.user_id ? (
                    <select
                      aria-label={`Role of ${m.full_name}`}
                      className={`${field} w-36`}
                      value={m.role}
                      onChange={(e) =>
                        run(() => api.updateMember(m.id, e.target.value), "Role updated.")
                      }
                    >
                      <option value="member">Member</option>
                      <option value="admin">Admin</option>
                      {me.role === "owner" && <option value="owner">Owner</option>}
                    </select>
                  ) : (
                    <span className="capitalize">{m.role}</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-[#5A6075]">
                  {m.last_login_at ? new Date(m.last_login_at).toLocaleDateString() : "Never"}
                </td>
                <td className="px-3 py-2.5 text-right">
                  {isAdmin && m.user_id !== me.user_id && (
                    <button
                      type="button"
                      className={buttonDanger}
                      onClick={() => {
                        if (window.confirm(`Remove ${m.full_name} from the team?`)) {
                          run(() => api.removeMember(m.id), "Member removed.");
                        }
                      }}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {isAdmin && (
        <section className={`${card} flex flex-col gap-4 p-6`}>
          <h2 className="font-semibold">Invite someone</h2>
          <form onSubmit={invite} className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-[260px] flex-1 flex-col gap-1">
              <label htmlFor="inv-email" className="text-xs font-semibold text-[#3A4057]">
                Email
              </label>
              <input
                id="inv-email"
                type="email"
                required
                className={field}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="inv-role" className="text-xs font-semibold text-[#3A4057]">
                Role
              </label>
              <select
                id="inv-role"
                className={field}
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <button type="submit" className={buttonPrimary}>
              Send invitation
            </button>
          </form>
          {created?.link && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg bg-[#F6F7FB] p-3 text-sm">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{created.link}</span>
              <button
                type="button"
                className={buttonSecondary}
                onClick={() =>
                  navigator.clipboard
                    .writeText(created.link ?? "")
                    .then(() => setMessage("Link copied. It works once, for 7 days."))
                    .catch(() => setMessage("Copy the link by hand."))
                }
              >
                Copy link
              </button>
            </div>
          )}
          {invites.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-semibold">Waiting to be accepted</h3>
              <ul className="flex flex-col gap-2">
                {invites.map((i) => (
                  <li
                    key={i.id}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <span>
                      {i.email} · <span className="capitalize">{i.role}</span> · expires{" "}
                      {new Date(i.expires_at).toLocaleDateString()}
                    </span>
                    <button
                      type="button"
                      className={buttonSecondary}
                      onClick={() => run(() => api.revokeInvite(i.id), "Invitation revoked.")}
                    >
                      Revoke
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
