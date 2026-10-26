/** Home = a dashboard: where you are, what is next, what needs attention. Details live one click away. */

import { useEffect, useState } from 'react'
import { api, fmtDate, money } from '../api'
import ShieldCard from '../components/ShieldCard'
import { Card, Kpi, Pill } from '../components/ui'
import { pick, useApp } from '../i18n'
import type { Inspection, Lease, Task } from '../types'

export function DeadlineTable({ tasks, limit, onToggle }: { tasks: Task[]; limit?: number; onToggle?: (key: string) => void }) {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const rows = limit ? tasks.slice(0, limit) : tasks
  if (!rows.length) return <p className="muted small">{ko ? '가까운 기한이 없습니다.' : 'Nothing due soon.'}</p>
  return (
    <table className="tbl deadlines">
      <thead>
        <tr>
          {onToggle && <th />}
          <th>{ko ? '날짜' : 'Date'}</th>
          <th>{ko ? '할 일' : 'To do'}</th>
          <th className="num">{ko ? '금액' : 'Amount'}</th>
          <th className="num">{ko ? '남은 날' : 'Left'}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((x) => {
          const late = !x.done && x.days_left !== null && x.days_left < 0
          const soon = !x.done && x.days_left !== null && x.days_left >= 0 && x.days_left <= 7
          return (
            <tr key={x.key} className={`${x.done ? 'done' : ''} ${late ? 'late' : ''} ${soon ? 'soon' : ''}`}>
              {onToggle && <td><input type="checkbox" checked={x.done} onChange={() => onToggle(x.key)} /></td>}
              <td className="nowrap">{fmtDate(x.date, lang)}</td>
              <td>{pick(x as unknown as Record<string, unknown>, 'title', lang)}</td>
              <td className="num">{x.amount ? money(x.amount) : ''}</td>
              <td className="num nowrap">
                {x.done ? '✓' : x.days_left === null ? '' : x.days_left < 0 ? (ko ? `${-x.days_left}일 지남` : `${-x.days_left}d late`) : x.days_left === 0 ? (ko ? '오늘' : 'today') : `D-${x.days_left}`}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

interface SubletLite {
  id: number; role: string; status: string; escrow_balance: number; start_date: string; end_date: string; deposit: number
  steps: { key: string; date: string | null }[]
  settlement: { to_subtenant: number; proposed_on: string } | null
  utility_shares: { subtenant_share: number; paid_on: string | null; due: string | null }[]
}
interface DisputeLite { result: { money: { refund_requested: number; approved_total: number; claimed_total: number }; facts: { statement_late?: boolean; days_late?: number } } | null }

const STEP_NAMES: Record<string, [string, string]> = {
  lease: ['Lease signed', '계약 체결'], move_in: ['Move-in record', '입주 기록'], living: ['Living', '거주'],
  move_out: ['Move-out record', '퇴거 기록'], deposit: ['Deposit back', '보증금 반환'],
  listed: ['Listed', '게시'], matched: ['Matched', '매칭'], deposit_in: ['Deposit in escrow', '보증금 보관'],
  moved_in: ['Moved in', '입주'], returned: ['Returned', '반환'], settled: ['Settled', '정산'],
}

const SUBLET_STATUS: Record<string, [string, string]> = {
  open: ['looking', '세입자 찾는 중'], matched: ['matched', '매칭됨'], funded: ['funded', '보증금 보관'], active: ['active', '거주 중'],
  return_due: ['settle now', '정산 필요'], settlement_proposed: ['proposal sent', '정산안 제시'], disputed: ['disputed', '이의 제기'], closed: ['closed', '종료'],
}

export default function Home() {
  const { lang, me, go } = useApp()
  const ko = lang === 'ko'
  const mode = me?.user.mode ?? 'tenant'
  const today = me?.today ?? ''
  const [lease, setLease] = useState<Lease | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [insps, setInsps] = useState<Inspection[]>([])
  const [sublets, setSublets] = useState<SubletLite[]>([])
  const [disputes, setDisputes] = useState<DisputeLite[]>([])
  const [hasPrecheck, setHasPrecheck] = useState(true)

  useEffect(() => {
    api.get<{ lease: Lease | null }>('/api/leases/current').then((r) => setLease(r.lease))
    api.get<{ tasks: Task[] }>('/api/calendar').then((r) => setTasks(r.tasks))
    api.get<Inspection[]>('/api/inspections').then(setInsps)
    api.get<SubletLite[]>('/api/sublets').then(setSublets)
    if (mode !== 'subtenant') api.get<DisputeLite[]>('/api/disputes').then(setDisputes)
    api.get<{ precheck: unknown }>('/api/precheck').then((r) => setHasPrecheck(Boolean(r.precheck)))
  }, [mode])

  const card = lease?.card
  const s = sublets[0]
  const open = tasks.filter((t) => !t.done && t.days_left !== null)
  const upcoming = open.filter((t) => t.days_left! >= -14)
  const next = upcoming.find((t) => t.days_left! >= 0) ?? upcoming[0]
  const due30 = open.filter((t) => t.days_left! >= 0 && t.days_left! <= 30 && t.amount).reduce((a, t) => a + (t.amount ?? 0), 0)
  const findings = insps.reduce((a, i) => a + (i.result?.findings.length ?? 0), 0)
  const dispute = disputes.find((d) => d.result)?.result
  const start = card?.lease_start, end = card?.lease_end
  const dayN = start && today ? Math.floor((Date.parse(today) - Date.parse(start)) / 86400000) + 1 : null
  const daysLeft = end && today ? Math.ceil((Date.parse(end) - Date.parse(today)) / 86400000) : null

  // Things that need a human decision, most important first (max 3).
  const alerts: { tone: 'bad' | 'warn'; text: string; page: string }[] = []
  if (dispute?.facts.statement_late)
    alerts.push({ tone: 'bad', page: 'court', text: ko ? `공제 내역서가 법정 기한보다 ${dispute.facts.days_late}일 늦게 왔습니다` : `The deduction statement came ${dispute.facts.days_late} days late` })
  const overdue = open.filter((t) => t.days_left! < 0 && t.days_left! >= -30)
  if (overdue.length) alerts.push({ tone: 'warn', page: 'lease', text: ko ? `지난 기한 ${overdue.length}건: ${pick(overdue[0] as unknown as Record<string, unknown>, 'title', lang)}` : `${overdue.length} overdue: ${overdue[0].title_en}` })
  if (card?.red_flags.length && mode !== 'subtenant' && dayN !== null && dayN <= 3)
    alerts.push({ tone: 'warn', page: 'lease', text: ko ? `계약서에 주의할 조항 ${card.red_flags.length}개` : `${card.red_flags.length} lease terms to watch` })
  if (!hasPrecheck && !dispute && daysLeft !== null && daysLeft >= 0 && daysLeft <= 30)
    alerts.push({ tone: 'warn', page: 'court', text: ko ? `퇴거 D-${daysLeft}: 퇴거 전 진단으로 수리비를 아끼세요 (고칠까, 물어줄까?)` : `Move-out in ${daysLeft} days: run the precheck — fix it or pay for it?` })
  const insp0 = insps.find((i) => i.result?.injection_blocked)
  if (insp0) alerts.push({ tone: 'warn', page: 'inspections', text: ko ? '사진 속 AI 지시문을 검문소가 차단했습니다' : 'The checkpoint blocked text addressed to the AI in a photo' })

  const steps: { key: string; date: string | null | undefined; page: string }[] =
    mode === 'subtenant' && s
      ? s.steps.map((st) => ({ key: st.key === 'deposit' ? 'deposit_in' : st.key, date: st.date, page: st.key === 'returned' || st.key === 'moved_in' ? 'inspections' : 'sublet' }))
      : [
          { key: 'lease', date: card ? (lease as Lease & { signed_on?: string }).signed_on ?? start : null, page: 'lease' },
          { key: 'move_in', date: insps.find((i) => i.kind === 'move_in' && i.result)?.inspected_on, page: 'inspections' },
          { key: 'living', date: start && today > start ? start : null, page: 'bills' },
          { key: 'move_out', date: insps.find((i) => i.kind === 'move_out' && i.result)?.inspected_on, page: 'inspections' },
          { key: 'deposit', date: dispute ? (ko ? '진행 중' : 'in progress') : null, page: 'court' },
        ]

  return (
    <div className="home">
      <div className="home-head">
        <div>
          <h2>{ko ? `${me?.user.name}님` : `Hi ${me?.user.name}`}</h2>
          <p className="muted small">
            {mode === 'subtenant' && s
              ? (ko ? `서브렛 ${fmtDate(s.start_date, lang)} – ${fmtDate(s.end_date, lang)}` : `Sublet ${fmtDate(s.start_date, lang)} – ${fmtDate(s.end_date, lang)}`)
              : card
                ? (dayN === null || dayN <= 0
                    ? (ko ? `입주 전 · ${fmtDate(start, lang)} 시작` : `Starts ${fmtDate(start, lang)}`)
                    : daysLeft !== null && daysLeft < 0
                      ? (ko ? `임대 종료 · ${fmtDate(end, lang)}` : `Lease ended ${fmtDate(end, lang)}`)
                      : (ko ? `임대 ${dayN}일차 · 종료까지 ${daysLeft}일` : `Lease day ${dayN} · ${daysLeft} days to go`))
                : (ko ? '계약서를 올리면 시작됩니다' : 'Upload your lease to start')}
          </p>
        </div>
      </div>

      <div className="kpis">
        <Kpi label={ko ? '다음 할 일' : 'Next'} onClick={() => go('lease')}
          value={next ? (next.days_left! < 0 ? (ko ? `${-next.days_left!}일 지남` : `${-next.days_left!}d late`) : next.days_left === 0 ? (ko ? '오늘' : 'Today') : `D-${next.days_left}`) : '—'}
          hint={next ? pick(next as unknown as Record<string, unknown>, 'title', lang) : (ko ? '없음' : 'Nothing')} tone={next ? (next.days_left! < 0 ? 'bad' : next.days_left! <= 3 ? 'warn' : 'plain') : 'plain'} />
        <Kpi label={ko ? '30일 안에 낼 돈' : 'Due in 30 days'} value={money(due30)} onClick={() => go(mode === 'subtenant' ? 'bills' : 'lease')}
          hint={ko ? '월세·공과금·분담금' : 'rent, bills, shares'} />
        {mode === 'subtenant' && s ? (
          <Kpi label={ko ? '내 보증금 (에스크로)' : 'My deposit (escrow)'} value={money(s.escrow_balance)} onClick={() => go('sublet')}
            hint={s.settlement ? (ko ? `정산안: ${money(s.settlement.to_subtenant)} 반환` : `Proposal: ${money(s.settlement.to_subtenant)} back`) : (ko ? 'Rentrail이 보관 중' : 'held by Rentrail')}
            tone={s.settlement ? 'warn' : 'good'} />
        ) : (
          <Kpi label={ko ? '보증금' : 'Deposit'} value={money(card?.security_deposit)} onClick={() => go('court')}
            hint={dispute ? (ko ? `반환 요청 ${money(dispute.money.refund_requested)}` : `asking ${money(dispute.money.refund_requested)} back`) : (ko ? '집주인 에스크로에 보관' : 'in the landlord’s escrow')}
            tone={dispute ? 'warn' : 'plain'} />
        )}
        <Kpi label={ko ? '점검 기록' : 'Records'} value={`${insps.length}`} onClick={() => go('inspections')}
          hint={ko ? `하자 ${findings}건 기록` : `${findings} defects on record`} />
      </div>

      {alerts.length > 0 && (
        <div className="alerts">
          {alerts.slice(0, 3).map((a, i) => (
            <button key={i} className={`alert-row ${a.tone}`} onClick={() => go(a.page)}>
              <span>{a.tone === 'bad' ? '⚠️' : '•'}</span> {a.text} <span className="muted">→</span>
            </button>
          ))}
        </div>
      )}

      <div className="home-grid">
        <Card title={ko ? '다가오는 일' : 'Coming up'} right={mode !== 'subtenant' && <button className="btn ghost small" onClick={() => go('lease')}>{ko ? '전체' : 'All'} →</button>}>
          <DeadlineTable tasks={upcoming} limit={5} />
        </Card>
        <div>
        <ShieldCard />
        <Card title={ko ? '진행 상황' : 'Progress'}>
          <ol className="vsteps">
            {steps.map((st) => (
              <li key={st.key} className={st.date ? 'done' : ''} onClick={() => go(st.page)}>
                <span className="vdot">{st.date ? '✓' : ''}</span>
                <span className="grow">{(STEP_NAMES[st.key] ?? [st.key, st.key])[ko ? 1 : 0]}</span>
                <span className="muted small">{st.date && /\d{4}-/.test(st.date) ? fmtDate(st.date, lang) : st.date ?? ''}</span>
              </li>
            ))}
          </ol>
          {s && mode === 'sublessor' && (
            <p className="small muted">🤝 {ko ? '서브렛' : 'Sublet'} <Pill tone="amber">{(SUBLET_STATUS[s.status] ?? [s.status, s.status])[ko ? 1 : 0]}</Pill> {ko ? '에스크로' : 'escrow'} {money(s.escrow_balance)}</p>
          )}
        </Card>
        </div>
      </div>
    </div>
  )
}
