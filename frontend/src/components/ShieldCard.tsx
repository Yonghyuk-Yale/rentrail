/** Deposit Shield: how well your deposit is protected today (0-100), computed by code from your records.
 * The ring fills as you add evidence; the shield levels up from paper to gold. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../i18n'
import { Card, Disclosure } from './ui'

interface Check {
  key: string; points: number; earned: number; done: boolean; title_en: string; title_ko: string
  fix_en: string; fix_ko: string; page: string; phase: 'now' | 'later'
}
interface Shield { score: number; level: 'paper' | 'wood' | 'steel' | 'gold'; level_en: string; level_ko: string; checks: Check[]; next: Check[] }

const LEVEL = {
  paper: { icon: '📄', color: '#94a3b8' },
  wood: { icon: '🪵', color: '#b45309' },
  steel: { icon: '🛡️', color: '#286dc0' },
  gold: { icon: '🏆', color: '#c9a227' },
} as const

function Ring({ score, color }: { score: number; color: string }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const t = window.setTimeout(() => setShown(score), 60) // let the ring animate in
    return () => window.clearTimeout(t)
  }, [score])
  const r = 42, c = 2 * Math.PI * r
  return (
    <svg className="shield-ring" viewBox="0 0 100 100" width="104" height="104" role="img" aria-label={`${score} / 100`}>
      <circle cx="50" cy="50" r={r} fill="none" stroke="#e8eef6" strokeWidth="10" />
      <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - shown / 100)} transform="rotate(-90 50 50)" />
      <text x="50" y="49" textAnchor="middle" className="shield-num">{score}</text>
      <text x="50" y="65" textAnchor="middle" className="shield-of">/ 100</text>
    </svg>
  )
}

export default function ShieldCard() {
  const { lang, go } = useApp()
  const ko = lang === 'ko'
  const [s, setS] = useState<Shield | null>(null)
  useEffect(() => {
    api.get<Shield>('/api/shield').then(setS)
  }, [])
  if (!s) return null
  const lv = LEVEL[s.level]
  const now = s.checks.filter((c) => c.phase === 'now')
  const later = s.checks.filter((c) => c.phase === 'later')
  return (
    <Card title={ko ? '보증금 방패' : 'Deposit Shield'} className="shield-card">
      <div className="shield-top">
        <Ring score={s.score} color={lv.color} />
        <div className="grow">
          <div className="shield-level" style={{ color: lv.color }}>{lv.icon} {ko ? s.level_ko : s.level_en}</div>
          <p className="small muted">{ko ? '기록이 탄탄할수록 보증금을 지키기 쉽습니다.' : 'The stronger your records, the safer your deposit.'}</p>
          {s.next.map((c) => (
            <button key={c.key} className="shield-next" onClick={() => go(c.page)}>
              <span>＋{Math.round(c.points - c.earned)}</span> {ko ? c.title_ko : c.title_en}
              {(ko ? c.fix_ko : c.fix_en) && <span className="muted"> — {ko ? c.fix_ko : c.fix_en}</span>}
            </button>
          ))}
          {s.next.length === 0 && <p className="small ok">✓ {ko ? '지금 할 수 있는 건 다 했습니다!' : 'Everything you can do today is done!'}</p>}
        </div>
      </div>
      <Disclosure summary={<span className="small">{ko ? '점수 내역' : 'How the score works'}</span>} count={now.filter((c) => c.done).length}>
        <table className="tbl">
          <tbody>
            {now.map((c) => (
              <tr key={c.key} className={c.done ? '' : 'muted'}>
                <td>{c.done ? '✅' : c.earned > 0 ? '◐' : '○'}</td>
                <td>{ko ? c.title_ko : c.title_en}</td>
                <td className="num">{Math.round(c.earned)}/{c.points}</td>
              </tr>
            ))}
            {later.map((c) => (
              <tr key={c.key} className="muted">
                <td>⏳</td>
                <td>{ko ? c.title_ko : c.title_en} <span className="small">({ko ? '퇴거 무렵' : 'near move-out'})</span></td>
                <td className="num">—</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">{ko ? 'AI 없이 코드로만 계산합니다.' : 'Plain code, no AI.'}</p>
      </Disclosure>
    </Card>
  )
}
