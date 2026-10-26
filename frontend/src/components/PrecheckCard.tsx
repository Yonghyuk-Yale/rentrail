/** Move-out precheck: for every damage, fix it yourself, hire someone, or let it be deducted?
 * Counsel Dan picks the repair category and judges DIY / wear and tear; every dollar comes from code. */

import { useEffect, useState } from 'react'
import { api, fileUrl, fmtDate, money } from '../api'
import { useApp } from '../i18n'
import type { Evidence } from '../types'
import RunPanel, { useRun } from './RunPanel'
import { Card, Disclosure, Err, EvidenceThumb, Kpi, Pill, RowItem } from './ui'

interface PItem {
  finding: { room: string; item: string; damage_type: string; evidence_id: number; location: string }
  status: string; reason_en: string; reason_ko: string; earlier_evidence_id: number | null
  label_en: string; label_ko: string; charge_range: [number, number]; pro_range: [number, number]
  diy_cost: number | null; diy_minutes: number | null; difficulty: string
  action: 'fix_yourself' | 'hire_pro' | 'let_deduct' | 'covered' | 'wear'
  expected_charge: number; plan_cost: number; saves: number; during_sublet?: boolean
  steps_en: string[]; steps_ko: string[]; tip_en: string; tip_ko: string; lease_pages: number[]; law_ids: string[]
}
interface Precheck {
  id: number; run_id: number; created_on: string; move_out_date: string | null; days_to_move_out: number | null
  items: PItem[]; totals: { if_nothing: number; with_plan: number; saves: number; from_sublet_escrow?: number }
  summary_en: string; summary_ko: string; table_note_en: string; table_note_ko: string
}
interface Rec { id: number; kind: string; inspected_on: string }

const ACTION: Record<PItem['action'], { en: string; ko: string; icon: string; tone: 'green' | 'blue' | 'amber' | 'gray' }> = {
  fix_yourself: { en: 'Fix it yourself', ko: '직접 고치기', icon: '🧰', tone: 'green' },
  hire_pro: { en: 'Hire a pro', ko: '업체에 맡기기', icon: '👷', tone: 'blue' },
  let_deduct: { en: 'Let it be deducted', ko: '공제받고 금액 확인', icon: '💸', tone: 'amber' },
  covered: { en: 'Already on record', ko: '이미 기록된 하자', icon: '📸', tone: 'gray' },
  wear: { en: 'Normal wear', ko: '통상 마모', icon: '✅', tone: 'gray' },
}
const KIND: Record<string, [string, string]> = {
  move_in: ['Move-in', '입주'], move_out: ['Move-out', '퇴거'], sublet_handoff: ['Sublet hand-off', '서브렛 인계'], sublet_return: ['Sublet return', '서브렛 반환'],
}

export default function PrecheckCard({ onOpen, compact, focusRun }: { onOpen: (e: Evidence) => void; compact?: boolean; focusRun?: number | null }) {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const [pc, setPc] = useState<Precheck | null>(null)
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [sugg, setSugg] = useState<{ earlier: Rec | null; later: Rec | null }>({ earlier: null, later: null })
  const [runId, setRunId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = () => api.get<{ precheck: Precheck | null; evidence: Evidence[]; suggested: { earlier: Rec | null; later: Rec | null } }>('/api/precheck')
    .then((r) => { setPc(r.precheck); setEvidence(r.evidence); setSugg(r.suggested) })
  useEffect(() => {
    load()
  }, [])
  useEffect(() => {
    if (focusRun) setRunId(focusRun)
  }, [focusRun])
  const run = useRun(runId, load)
  const ev = (id: number | null | undefined) => (id ? evidence.find((e) => e.id === id) : undefined)
  const rec = (r: Rec | null) => (r ? `${(KIND[r.kind] ?? [r.kind, r.kind])[ko ? 1 : 0]} · ${fmtDate(r.inspected_on, lang)}` : '—')

  const start = async () => {
    try {
      setError(null)
      setRunId((await api.post<{ run_id: number }>('/api/precheck', {})).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const canRun = Boolean(sugg.earlier && sugg.later)
  const runBtn = (
    <button className={`btn small ${pc ? 'ghost' : 'primary'}`} disabled={!canRun || run?.status === 'running'} onClick={start}
      title={canRun ? `${rec(sugg.earlier)} → ${rec(sugg.later)}` : ''}>
      🔧 {pc ? (ko ? '다시 진단' : 'Run again') : (ko ? '진단 받기' : 'Run precheck')}
    </button>
  )

  const body = (
    <>
      <Err error={error} />
      {run?.status === 'running' && <RunPanel run={run} compact />}
      {!pc ? (
        <div className="precheck-empty">
          <p className="small">{ko
            ? '떠나기 2~4주 전에 받으세요. 입주 기록과 최근 기록을 비교해 하자마다 "직접 고치면 얼마, 그냥 두면 얼마"를 알려드립니다.'
            : 'Run it 2-4 weeks before you leave. Rentrail compares your move-in record with your latest one and prices each damage: fix it yourself vs. let it be deducted.'}</p>
          <p className="small muted">{canRun ? `${rec(sugg.earlier)} → ${rec(sugg.later)}` : (ko ? '입주 기록과, 그 뒤에 점검을 마친 기록이 하나 더 필요합니다.' : 'Needs a move-in record and a newer analysed record.')}</p>
        </div>
      ) : (
        <>
          <div className="kpis">
            <Kpi label={ko ? '그냥 두면 예상 청구' : 'If you do nothing'} value={money(pc.totals.if_nothing)} tone="warn" hint={ko ? '집주인 공제 예상 (중간값)' : 'likely deductions (mid-range)'} />
            <Kpi label={ko ? '계획대로 하면' : 'With the plan'} value={money(pc.totals.with_plan)} hint={ko ? '직접 수리 자재비 + 업체 비용' : 'DIY materials + pro repairs'} />
            <Kpi label={ko ? '아낄 수 있는 돈' : 'You could save'} value={money(pc.totals.saves)} tone="good"
              hint={pc.totals.from_sublet_escrow ? `${ko ? '서브렛 에스크로에서 청구 가능' : 'claimable from the sublet escrow'} ${money(pc.totals.from_sublet_escrow)}` : undefined} />
            <Kpi label={ko ? '퇴거까지' : 'Until move-out'} value={pc.days_to_move_out === null ? '—' : pc.days_to_move_out >= 0 ? `D-${pc.days_to_move_out}` : (ko ? '지남' : 'passed')}
              hint={`${ko ? '진단일' : 'checked'} ${fmtDate(pc.created_on, lang)}`} tone={pc.days_to_move_out !== null && pc.days_to_move_out <= 7 ? 'warn' : 'plain'} />
          </div>
          <p className="lead-line">{ko ? pc.summary_ko : pc.summary_en}</p>
          {pc.items.map((it, i) => {
            const a = ACTION[it.action]
            const later = ev(it.finding.evidence_id)
            const before = ev(it.earlier_evidence_id)
            return (
              <RowItem key={i}
                left={later ? <img className="mini-thumb" src={fileUrl(later.file_id, later.sha256)} alt="" /> : a.icon}
                main={<>{it.finding.room} · {ko ? it.label_ko : it.label_en}</>}
                sub={it.action === 'fix_yourself'
                  ? `${ko ? '자재비' : 'materials'} ${money(it.diy_cost)} · ${it.diy_minutes}${ko ? '분' : ' min'} · ${ko ? '그냥 두면' : 'else'} ~${money(it.expected_charge)}`
                  : it.action === 'hire_pro'
                    ? `${ko ? '업체' : 'pro'} ${money(it.pro_range[0])}–${money(it.pro_range[1])} · ${ko ? '그냥 두면' : 'else'} ~${money(it.expected_charge)}`
                    : (ko ? it.reason_ko : it.reason_en)}
                right={<>
                  {it.during_sublet && <Pill tone="purple">{ko ? '서브렛 에스크로 청구' : 'Claim from sublet escrow'}</Pill>}
                  <Pill tone={a.tone}>{a.icon} {ko ? a.ko : a.en}</Pill>
                  {it.saves > 0 && <strong className="ok">−{money(it.saves)}</strong>}
                </>}>
                <div className="finding-detail">
                  <div className="pair-imgs">
                    <div><div className="small muted">{ko ? '이전 (같은 위치)' : 'Before'}</div>{before ? <EvidenceThumb ev={before} onOpen={onOpen} /> : <div className="thumb empty-thumb">—</div>}</div>
                    <div><div className="small muted">{ko ? '최근' : 'Latest'}</div>{later && <EvidenceThumb ev={later} onOpen={onOpen} />}</div>
                  </div>
                  <div className="grow">
                    {(ko ? it.steps_ko : it.steps_en).length > 0 && (
                      <ol className="lines">{(ko ? it.steps_ko : it.steps_en).map((s, j) => <li key={j}>{s}</li>)}</ol>
                    )}
                    <p className="small">💡 {ko ? it.tip_ko : it.tip_en}</p>
                    {it.during_sublet && <p className="small muted">🤝 {ko ? '서브렛 인계 기록에 없던 하자 → 서브렛 세입자의 에스크로 보증금에서 청구할 수 있습니다 (CT-47a-21-a7).' : 'Not in the sublet hand-off record → claim it from the subtenant’s escrow deposit (CT-47a-21-a7).'}</p>}
                    <p className="small muted">{ko ? '집주인 청구 예상' : 'Typical landlord charge'} {money(it.charge_range[0])}–{money(it.charge_range[1])}</p>
                    <div>{it.lease_pages.map((p) => <Pill key={p} tone="gray">lease p.{p}</Pill>)} {it.law_ids.map((l) => <Pill key={l} tone="purple">{l}</Pill>)}</div>
                  </div>
                </div>
              </RowItem>
            )
          })}
          <p className="small muted small-top">ⓘ {ko ? pc.table_note_ko : pc.table_note_en} {ko ? '금액은 코드가 표에서 계산하고, AI는 수리 종류와 직접 수리 가능 여부만 판단합니다.' : 'Code prices every item from the table; the AI only picks the repair type and whether DIY is safe.'}</p>
        </>
      )}
    </>
  )

  if (compact)
    return (
      <Card>
        <Disclosure summary={`🔧 ${ko ? '퇴거 전 진단: 고칠까, 물어줄까?' : 'Move-out precheck: fix it or pay for it?'}${pc ? ` · ${fmtDate(pc.created_on, lang)}` : ''}`} right={runBtn}>
          {body}
        </Disclosure>
      </Card>
    )
  return (
    <Card title={`🔧 ${ko ? '퇴거 전 진단: 고칠까, 물어줄까?' : 'Move-out precheck: fix it or pay for it?'}`} right={runBtn}>
      {body}
    </Card>
  )
}
