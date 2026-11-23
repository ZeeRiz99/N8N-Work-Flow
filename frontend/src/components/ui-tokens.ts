// Shared class names from docs/design/DESIGN_REFERENCE.md (controls are 44px tall, 1px border).
// Field border #8A90A6 = 3.2:1 on white (WCAG 1.4.11 non-text contrast for input boundaries).
export const field =
  "min-h-11 w-full rounded-lg border border-[#8A90A6] bg-white px-3 text-[#1A1D2B]";
export const buttonSecondary =
  "inline-flex min-h-11 items-center justify-center rounded-lg border border-[#CDD2E0] bg-white px-4 font-medium disabled:opacity-60";
export const buttonPrimary =
  "inline-flex min-h-11 items-center justify-center rounded-lg bg-[#4338CA] px-4 font-semibold text-white disabled:opacity-60";
export const buttonDanger =
  "inline-flex min-h-11 items-center justify-center rounded-lg border border-[#CDD2E0] bg-white px-4 font-semibold text-[#A32A12] disabled:opacity-60";
export const card = "rounded-xl border border-[#E3E6EF] bg-white";

export function timeAgo(iso: string): string {
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 45) return "Just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}
