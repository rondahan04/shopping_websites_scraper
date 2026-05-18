/** Terminal-window + goat-horns SVG logo — matches the cyber scraper aesthetic. */
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
      {/* Dark card background with subtle mint border */}
      <rect width="64" height="64" rx="14" fill="#041520" />
      <rect width="64" height="64" rx="14" fill="none" stroke="#7ee0d0" strokeWidth="0.75" strokeOpacity="0.3" />

      {/* Left goat horn — sweeps up-left, curls back inward */}
      <path d="M 15 9 Q 1 0 18 4" stroke="#7ee0d0" strokeWidth="2.4" strokeLinecap="round" />
      {/* Left horn inner curl hint */}
      <path d="M 18 4 Q 22 5 20 9" stroke="#7ee0d0" strokeWidth="1.4" strokeLinecap="round" strokeOpacity="0.5" />

      {/* Right goat horn — mirror */}
      <path d="M 49 9 Q 63 0 46 4" stroke="#7ee0d0" strokeWidth="2.4" strokeLinecap="round" />
      {/* Right horn inner curl hint */}
      <path d="M 46 4 Q 42 5 44 9" stroke="#7ee0d0" strokeWidth="1.4" strokeLinecap="round" strokeOpacity="0.5" />

      {/* Terminal screen body */}
      <rect x="8" y="10" width="48" height="46" rx="9" fill="#020c10" />

      {/* Title bar */}
      <rect x="8" y="10" width="48" height="13" rx="9" fill="#0b2d35" />
      <rect x="8" y="18" width="48" height="5" fill="#0b2d35" />

      {/* Traffic-light dots */}
      <circle cx="16" cy="17" r="2.2" fill="#ff6b4a" opacity="0.9" />
      <circle cx="23" cy="17" r="2.2" fill="#ffd700" opacity="0.55" />
      <circle cx="30" cy="17" r="2.2" fill="#00FF41" opacity="0.55" />

      {/* >_ prompt — main identity glyph */}
      <text
        x="12"
        y="37"
        fill="#ff6b4a"
        fontSize="13"
        fontFamily="ui-monospace, 'Fira Code', monospace"
        fontWeight="700"
      >
        &gt;_
      </text>

      {/* Blinking cursor block */}
      <rect x="34" y="27" width="5" height="8" rx="1" fill="#7ee0d0" opacity="0.85" />

      {/* Faux code lines */}
      <rect x="12" y="43" width="24" height="1.5" rx="0.75" fill="#7ee0d0" opacity="0.38" />
      <rect x="12" y="48" width="34" height="1.5" rx="0.75" fill="#7ee0d0" opacity="0.2" />
      <rect x="12" y="53" width="16" height="1.5" rx="0.75" fill="#ff6b4a" opacity="0.32" />
    </svg>
  );
}
