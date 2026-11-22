import Link from "next/link";
// Phase 3 home: links into the walking skeleton. The real dashboard follows docs/design/ in P4.
export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center bg-[#F6F7FB] px-4 py-16 font-[family-name:var(--font-public-sans)] text-[#1A1D2B]">
      <div className="flex max-w-md flex-col gap-4 rounded-xl border border-[#E3E6EF] bg-white p-8">
        <p className="text-sm font-semibold text-[#3730A3]">Phase 3 walking skeleton</p>
        <h1 className="text-2xl font-bold tracking-tight">Replyline</h1>
        <p className="text-[#3A4057]">
          Turn incoming leads into organized business opportunities. Submit the public form, then
          watch the lead get scored and alerted on the Leads page.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/leads"
            className="inline-flex min-h-11 items-center rounded-lg bg-[#4338CA] px-4 font-semibold text-white"
          >
            Open Leads
          </Link>
          <Link
            href="/f/harbor-web"
            className="inline-flex min-h-11 items-center rounded-lg border border-[#CDD2E0] bg-white px-4 font-medium"
          >
            Public lead form
          </Link>
        </div>
      </div>
    </main>
  );
}
