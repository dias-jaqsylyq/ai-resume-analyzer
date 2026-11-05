// Small inline SVG icons (no icon font, no external assets; CSP allows only 'self').

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
