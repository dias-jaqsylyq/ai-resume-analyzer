// Small inline SVG icons (no icon font, no external assets; CSP allows only 'self').
import type React from "react";

export function BrandMark({ size = 16 }: { size?: number }) {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
        <path d="M4 2.5h5l3 3v8a.5.5 0 0 1-.5.5h-7.5a.5.5 0 0 1-.5-.5v-10.5a.5.5 0 0 1 .5-.5Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        <path d="m5.75 9.25 1.5 1.5 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function Chevron({ direction = "right" }: { direction?: "left" | "right" }) {
  return (
    <svg className="chevron" width="8" height="14" viewBox="0 0 8 14" fill="none" aria-hidden="true">
      <path
        d={direction === "right" ? "m1.5 1.5 5 5.5-5 5.5" : "m6.5 1.5-5 5.5 5 5.5"}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type IconProps = { size?: number };

function Svg({ size = 20, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

export function GaugeIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3.5 13.5a6.5 6.5 0 1 1 13 0" />
      <path d="m10 13.5 3-4" />
    </Svg>
  );
}

export function ChecklistIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="m3.5 5.5 1.5 1.5 2.5-2.5M3.5 12.5 5 14l2.5-2.5M10.5 6h6M10.5 13h6" />
    </Svg>
  );
}

export function ShieldIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M10 2.75 4 5v4.5c0 3.6 2.6 6.6 6 7.75 3.4-1.15 6-4.15 6-7.75V5l-6-2.25Z" />
      <path d="m7.5 10 1.75 1.75L12.75 8.25" />
    </Svg>
  );
}

export function CheckIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="m5 10.5 3 3 7-7" />
    </Svg>
  );
}
