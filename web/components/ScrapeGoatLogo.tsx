/** Inline SVG logo — works without the generated PNG. */
export function ScrapeGoatLogo({ size = 48 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect width="64" height="64" rx="16" fill="#0f3d3e" />
      <path
        d="M18 38c2-8 8-14 16-14s14 6 16 14"
        stroke="#7ee0d0"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="28" cy="26" r="2.5" fill="#f5f0e6" />
      <circle cx="38" cy="26" r="2.5" fill="#f5f0e6" />
      <path
        d="M30 32h6"
        stroke="#f5f0e6"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M44 22l10 6-10 6V22z"
        fill="#ff6b4a"
      />
      <text
        x="14"
        y="52"
        fill="#7ee0d0"
        fontSize="9"
        fontFamily="ui-monospace, monospace"
      >
        {"{go}"}
      </text>
    </svg>
  );
}
