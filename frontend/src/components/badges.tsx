import type { AiStatus, Priority } from "@/lib/api";

// Colours from docs/design/DESIGN_REFERENCE.md. Priority is never colour alone: icon + word.
const PRIORITY = {
  high: { label: "High", bg: "#FCE7E1", fg: "#A32A12", bars: 3 },
  medium: { label: "Medium", bg: "#FDF0C8", fg: "#7A4A05", bars: 2 },
  low: { label: "Low", bg: "#E8EBF3", fg: "#444B63", bars: 1 },
  unscored: { label: "Not scored", bg: "#E8EBF3", fg: "#444B63", bars: 0 },
} as const;

export function PriorityBadge({ priority }: { priority: Priority }) {
  const p = PRIORITY[priority];
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-0.5 pr-2.5 pl-2 text-xs font-semibold"
      style={{ background: p.bg, color: p.fg }}
    >
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <rect
            key={i}
            x={1 + i * 3.7}
            y={7 - i * 3}
            width={2.6}
            height={4 + i * 3}
            rx={1}
            fill="currentColor"
            fillOpacity={i < p.bars ? 1 : 0.3}
          />
        ))}
      </svg>
      {p.label}
    </span>
  );
}

export function AiStatusPill({ status }: { status: AiStatus }) {
  if (status === "done") return null;
  const busy = status === "pending" || status === "processing";
  const style = busy
    ? { background: "#E6F0FA", color: "#1F4E79" }
    : { background: "#FFE9D6", color: "#8A3B00" };
  const label = busy ? "AI processing" : status === "failed" ? "AI failed, will retry" : "Skipped";
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={style}
    >
      {busy && (
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          aria-hidden="true"
          className="motion-safe:animate-spin"
        >
          <path d="M21 12a9 9 0 1 1-6.2-8.6" />
        </svg>
      )}
      {label}
    </span>
  );
}
