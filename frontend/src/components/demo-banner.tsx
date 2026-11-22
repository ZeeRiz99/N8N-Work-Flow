export function DemoBanner({ text }: { text: string }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-[#1A1D2B] px-6 py-2 text-[13px] text-white">
      <strong className="font-semibold">Demo data</strong>
      <span>{text}</span>
    </div>
  );
}
