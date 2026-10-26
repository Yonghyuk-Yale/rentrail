/** The Rentrail bench: the Yale bulldog mascot (from 99_Assets/YH_Bulldog) in costumes.
 * judge = Chief Justice (Boss), detective = Inspector, lawyer = Counsel,
 * clerk = Lease Analyst, sheriff = Escrow Sheriff (sublets), treasurer = bills & insurance.
 * costume 'gate' is not a bulldog: it is the Checkpoint that screens every input (see Gate.tsx). */

import type { Costume } from '../types'
import Gate from './Gate'

function shade(hex: string, amt: number): string {
  const n = parseInt(hex.replace('#', ''), 16)
  const ch = [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff].map((c) => {
    const target = amt >= 0 ? 255 : 0
    return Math.min(255, Math.max(0, Math.round(c + (target - c) * Math.abs(amt))))
  })
  return `#${ch.map((v) => v.toString(16).padStart(2, '0')).join('')}`
}

interface Props {
  costume?: Costume
  furColor?: string
  size?: number
  className?: string
  title?: string
}

const INK = '#2b2320'
const YALE = '#00356b'

export default function Bulldog({ costume = 'plain', furColor = '#e9d5b7', size = 72, className, title }: Props) {
  if (costume === 'gate') return <Gate size={size * 0.95} className={className} />
  const light = shade(furColor, 0.45)
  const dark = shade(furColor, -0.25)
  const robe = costume === 'judge'
  return (
    <svg viewBox="-8 -12 116 136" width={size} height={size * (136 / 116)} className={className} role="img" aria-label={title ?? costume}>
      {title ? <title>{title}</title> : null}
      {/* body (robe for the judge) */}
      <ellipse cx="50" cy="102" rx="44" ry="30" fill={robe ? '#1f2937' : furColor} />
      {robe && <path d="M50 78 L50 124" stroke="#111827" strokeWidth="1.2" />}
      <ellipse cx="29" cy="117" rx="10" ry="6" fill={light} />
      <ellipse cx="71" cy="117" rx="10" ry="6" fill={light} />

      {/* ears */}
      <path d="M13 27 q-4 17 10 27 q7 2 9 -5 q-4 -12 -3 -25 q-8 -4 -16 3 Z" fill={dark} />
      <path d="M87 27 q4 17 -10 27 q-7 2 -9 -5 q4 -12 3 -25 q8 -4 16 3 Z" fill={dark} />

      {/* judge wig sits behind the head */}
      {costume === 'judge' && (
        <g fill="#f8fafc" stroke="#cbd5e1" strokeWidth="0.8">
          {[14, 22, 30].map((y) => (
            <g key={y}>
              <circle cx={12} cy={y + 18} r={7} />
              <circle cx={88} cy={y + 18} r={7} />
            </g>
          ))}
        </g>
      )}

      {/* head */}
      <ellipse cx="50" cy="42" rx="36" ry="27" fill={furColor} />
      <ellipse cx="50" cy="57" rx="24" ry="14" fill={light} />
      <ellipse cx="32" cy="70" rx="14.5" ry="16.5" fill={light} />
      <ellipse cx="68" cy="70" rx="14.5" ry="16.5" fill={light} />
      <path d="M31 23 q19 -6 38 0" stroke={dark} strokeWidth="1.5" fill="none" opacity="0.4" strokeLinecap="round" />

      {/* eyes */}
      {costume === 'police' || costume === 'sheriff' || costume === 'detective' ? (
        <>
          <path d="M32 37 q5 -3 10 0" stroke={INK} strokeWidth="2.6" fill="none" strokeLinecap="round" />
          <path d="M58 37 q5 -3 10 0" stroke={INK} strokeWidth="2.6" fill="none" strokeLinecap="round" />
          <path d="M31 30 l11 3" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
          <path d="M69 30 l-11 3" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
        </>
      ) : (
        <>
          <path d="M32 36 q5 -7 10 0" stroke={INK} strokeWidth="2.5" fill="none" strokeLinecap="round" />
          <path d="M58 36 q5 -7 10 0" stroke={INK} strokeWidth="2.5" fill="none" strokeLinecap="round" />
        </>
      )}

      {/* nose + mouth */}
      <ellipse cx="50" cy="51" rx="9.5" ry="6.5" fill={INK} />
      <path d="M50 57.5 v4.5" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M50 62 q-10 8 -18 3" stroke={INK} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M50 62 q10 8 17 3" stroke={INK} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      {costume !== 'police' && costume !== 'judge' && (
        <path d="M52.5 62 q4.5 10 -0.5 17 q-6 3 -8 -4 q-0.5 -8 8.5 -13 Z" fill="#e8899f" stroke="#c96a83" strokeWidth="0.6" />
      )}

      {/* glasses */}
      {(costume === 'lawyer' || costume === 'clerk' || costume === 'treasurer') && (
        <g fill="none" stroke={INK} strokeWidth="1.8">
          {costume === 'clerk' ? (
            <>
              <rect x="29" y="30" width="15" height="11" rx="2" />
              <rect x="56" y="30" width="15" height="11" rx="2" />
            </>
          ) : (
            <>
              <circle cx="37" cy="35" r="7.5" />
              <circle cx="63" cy="35" r="7.5" />
            </>
          )}
          <path d="M44.5 35 q5.5 -3 11 0" />
        </g>
      )}

      {/* neckwear */}
      {costume === 'judge' ? (
        <g>
          <path d="M40 80 L50 98 L60 80 Z" fill="#ffffff" stroke="#cbd5e1" />
          <path d="M46 80 L50 90 L54 80" fill="none" stroke="#cbd5e1" />
        </g>
      ) : costume === 'lawyer' ? (
        <g>
          <path d="M38 80 L62 80 L50 88 Z" fill="#ffffff" />
          <path d="M47 86 L53 86 L55 108 L50 114 L45 108 Z" fill="#b91c1c" stroke="#7f1d1d" strokeWidth="0.8" />
        </g>
      ) : costume === 'police' ? (
        <g>
          <path d="M24 80 L76 80 L50 106 Z" fill="#1e3a8a" stroke="#172554" />
          <path d="M44 92 l6 -6 l6 6 l-2 8 h-8 Z" fill="#facc15" stroke="#a16207" strokeWidth="0.8" />
        </g>
      ) : (
        <g>
          <path d="M24 80 L76 80 L50 106 Z" fill={YALE} stroke="#002a56" strokeWidth="1" />
          {costume === 'sheriff' ? (
            <path d="M50 86 l2.4 5 5.4 .6 -4 3.6 1.2 5.3 -5 -2.8 -5 2.8 1.2 -5.3 -4 -3.6 5.4 -.6 Z" fill="#facc15" stroke="#a16207" strokeWidth="0.7" />
          ) : (
            <text x="50" y="99" textAnchor="middle" fontFamily="Georgia, serif" fontWeight={700} fontSize="14" fill="#fff">Y</text>
          )}
        </g>
      )}

      {/* hats */}
      {costume === 'police' && (
        <g>
          <path d="M20 18 Q50 -8 80 18 L78 24 L22 24 Z" fill="#1e3a8a" stroke="#172554" />
          <rect x="22" y="20" width="56" height="5" fill="#111827" />
          <path d="M24 25 Q50 34 76 25 L72 29 Q50 36 28 29 Z" fill="#0f172a" />
          <circle cx="50" cy="11" r="4.2" fill="#facc15" stroke="#a16207" strokeWidth="0.8" />
        </g>
      )}
      {costume === 'sheriff' && (
        <g>
          <ellipse cx="50" cy="19" rx="46" ry="7" fill="#92400e" />
          <path d="M28 18 Q30 -2 50 2 Q70 -2 72 18 Z" fill="#b45309" />
          <path d="M30 13 Q50 18 70 13" stroke="#78350f" strokeWidth="2.4" fill="none" />
        </g>
      )}
      {costume === 'detective' && (
        <g>
          <path d="M18 22 Q50 -10 82 22 Q50 14 18 22 Z" fill="#8b5e34" stroke="#5b3a1e" />
          <path d="M30 12 Q50 6 70 12 M26 17 Q50 10 74 17" stroke="#d6b88d" strokeWidth="1.2" fill="none" />
          <path d="M18 22 Q8 24 6 30 Q16 30 22 25 Z" fill="#7a4f2a" />
        </g>
      )}
      {costume === 'judge' && (
        <g fill="#f8fafc" stroke="#cbd5e1" strokeWidth="0.8">
          {[22, 34, 46, 58, 70, 78].map((x) => (
            <circle key={x} cx={x} cy={x === 22 || x === 78 ? 20 : 13} r={8} />
          ))}
        </g>
      )}
      {costume === 'clerk' && (
        <g>
          <path d="M26 16 Q50 2 74 16 L72 21 L28 21 Z" fill={YALE} />
          <rect x="44" y="1" width="12" height="5" fill={YALE} />
          <path d="M56 4 q10 4 12 16" stroke="#facc15" strokeWidth="1.5" fill="none" />
        </g>
      )}
      {costume === 'treasurer' && (
        <path d="M18 24 Q50 4 82 24 Q50 16 18 24 Z" fill="#16a34a" opacity="0.85" />
      )}

      {/* props in the paws */}
      {costume === 'judge' && (
        <g transform="rotate(-25 86 102)">
          <rect x="80" y="86" width="16" height="9" rx="2" fill="#92400e" stroke="#451a03" />
          <rect x="86.5" y="95" width="3" height="18" fill="#78350f" />
        </g>
      )}
      {costume === 'detective' && (
        <g>
          <circle cx="86" cy="96" r="9" fill="#e0f2fe" fillOpacity="0.55" stroke="#334155" strokeWidth="2.4" />
          <path d="M80 103 L72 112" stroke="#334155" strokeWidth="3.4" strokeLinecap="round" />
        </g>
      )}
      {costume === 'lawyer' && (
        <g>
          <rect x="-4" y="98" width="20" height="14" rx="2" fill="#7c2d12" stroke="#431407" />
          <path d="M2 98 v-3 h8 v3" fill="none" stroke="#431407" strokeWidth="1.5" />
        </g>
      )}
      {costume === 'clerk' && (
        <g>
          <rect x="80" y="92" width="14" height="20" rx="2" fill="#fef3c7" stroke="#b45309" />
          <path d="M83 98 h8 M83 102 h8 M83 106 h5" stroke="#b45309" strokeWidth="1" />
        </g>
      )}
      {costume === 'treasurer' && (
        <g>
          {[0, 4, 8].map((d) => (
            <ellipse key={d} cx="88" cy={110 - d} rx="8" ry="3" fill="#facc15" stroke="#a16207" />
          ))}
        </g>
      )}
      {costume === 'sheriff' && (
        <g>
          <rect x="78" y="94" width="16" height="16" rx="2.5" fill="#fde68a" stroke="#a16207" />
          <path d="M82 100 h8 v6 h-8 Z" fill="none" stroke="#a16207" />
          <circle cx="86" cy="103" r="1.3" fill="#a16207" />
        </g>
      )}
      {costume === 'police' && (
        <g>
          <rect x="80" y="98" width="12" height="16" rx="3" fill="#0f172a" />
          <circle cx="86" cy="103" r="2.2" fill="#ef4444" />
          <circle cx="86" cy="109" r="2.2" fill="#3b82f6" />
        </g>
      )}
    </svg>
  )
}
