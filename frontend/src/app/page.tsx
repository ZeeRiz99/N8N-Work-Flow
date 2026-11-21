import { Button } from "@/components/ui/button";

// Phase 2 placeholder. The real screens follow docs/design/ from Phase 4.
export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center bg-[#F6F7FB] px-4 py-16 font-[family-name:var(--font-public-sans)] text-[#1A1D2B]">
      <div className="flex max-w-md flex-col gap-4 rounded-xl border border-[#E3E6EF] bg-white p-8">
        <p className="text-sm font-semibold text-[#3730A3]">Phase 2 skeleton</p>
        <h1 className="text-2xl font-bold tracking-tight">Replyline</h1>
        <p className="text-[#3A4057]">
          Turn incoming leads into organized business opportunities. The dashboard arrives in Phase
          4.
        </p>
        <div>
          <Button>Coming soon</Button>
        </div>
      </div>
    </main>
  );
}
