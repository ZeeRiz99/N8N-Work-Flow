import type { Metadata } from "next";

import { LeadsTable } from "./leads-table";

export const metadata: Metadata = { title: "Leads · Replyline" };

export default function LeadsPage() {
  return <LeadsTable />;
}
