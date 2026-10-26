/** The Checkpoint: not an agent, an always-on inspection gate (plain code) that every input passes
 * before any AI reads it. Drawn as a booth with a barrier arm and a scanning beam. */

export default function Gate({ size = 72, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} className={className} role="img" aria-label="Checkpoint">
      <title>Checkpoint</title>
      {/* ground */}
      <rect x="6" y="104" width="108" height="6" rx="3" fill="#cbd5e1" />
      {/* booth */}
      <rect x="12" y="44" width="38" height="60" rx="4" fill="#00356b" />
      <path d="M8 46 L31 30 L54 46 Z" fill="#1d4f91" />
      <rect x="18" y="52" width="26" height="18" rx="2" fill="#e0f2fe" />
      <path d="M18 66 L44 54" stroke="#ffffff" strokeWidth="2" opacity="0.7" />
      <rect x="18" y="76" width="26" height="6" rx="2" fill="#facc15" />
      {/* scanning beam */}
      <path d="M44 60 L104 46 L104 74 Z" fill="#38bdf8" opacity="0.18" />
      <line x1="44" y1="60" x2="104" y2="60" stroke="#38bdf8" strokeWidth="1.5" strokeDasharray="4 3" />
      {/* barrier post + striped arm */}
      <rect x="52" y="78" width="8" height="26" rx="2" fill="#334155" />
      <g transform="rotate(-8 56 82)">
        <rect x="56" y="78" width="58" height="8" rx="4" fill="#ffffff" stroke="#b91c1c" strokeWidth="1" />
        {[62, 74, 86, 98].map((x) => <rect key={x} x={x} y="78" width="6" height="8" fill="#ef4444" />)}
      </g>
      {/* shield badge */}
      <path d="M92 8 L108 14 V26 C108 36 100 42 92 45 C84 42 76 36 76 26 V14 Z" fill="#15803d" stroke="#ffffff" strokeWidth="2" />
      <path d="M85 26 L90.5 31.5 L100 21" stroke="#ffffff" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
