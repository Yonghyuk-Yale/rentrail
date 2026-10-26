/** Deposit: four numbers, the landlord's items as one-line rows (click for the reasoning and the
 * evidence), and the ruling and the letter folded away. Subtenants get the sublet version. */

import { useEffect, useMemo, useState } from 'react'
import { api, fileUrl, fmtDate, money, takeFocus } from '../api'
import PrecheckCard from '../components/PrecheckCard'
import RunPanel, { useRun } from '../components/RunPanel'
import { Card, Disclosure, Err, EvidenceModal, EvidenceThumb, Kpi, PageHead, Pill, RowItem } from '../components/ui'
import { pick, useApp } from '../i18n'
import type { Comparison, Evidence, Inspection } from '../types'
import { kindLabel } from './Inspections'
import SubletCourt from './SubletCourt'

interface BriefItem {
  item: string
  amount_claimed: number
  verdict: 'contest' | 'accept' | 'partial'
  fair_amount: number
  reason_en: string
  reason_ko: string
  evidence_ids: number[]
  lease_pages: number[]
  law_ids: string[]
}
interface CaseResult {
  facts: Record<string, unknown>
  comparison: Comparison
  brief: { items: BriefItem[]; procedural_issues_en: string[]; procedural_issues_ko: string[] }
  ruling: { items: { item: string; approved_deduction: number; note_en: string; note_ko: string }[]; ruling_en: string; ruling_ko: string; letter_ko_summary: string; human_review_needed: boolean }
  money: { deposit: number; interest: number; claimed_total: number; approved_total: number; refund_requested: number; statute_double_damages: number | null }
  letter_en: string
  officer: { hidden_removed: string[]; instruction_lines: string[]; masked: Record<string, number> }
}
interface Dispute { id: number; status: string; facts: Record<string, string | number | null>; result: CaseResult | null; deduction_file_id: number }

const VERDICT_TONE = { contest: 'green', partial: 'amber', accept: 'gray' } as const
const VERDICT_LABEL = { contest: ['Contested', '이의 제기'], partial: ['Reduced', '감액'], accept: ['Fair', '인정'] } as const

export default function Court() {
  const { me } = useApp()
  if (me?.user.mode === 'subtenant') return <SubletCourt />
  return <LandlordCourt />
}

function LandlordCourt() {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const [disputes, setDisputes] = useState<Dispute[]>([])
  const [loaded, setLoaded] = useState(false)
  const [insps, setInsps] = useState<Inspection[]>([])
  const [runId, setRunId] = useState<number | null>(null)
  const [preRun, setPreRun] = useState<number | null>(null)
  const [open, setOpen] = useState<Evidence | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ move_in_id: '', move_out_id: '', termination_date: '', forwarding_address_date: '', statement_received_date: '', keys_returned_date: '', deposit: '' })
  const [file, setFile] = useState<File | null>(null)
  const [copied, setCopied] = useState(false)

  const load = () => {
    api.get<Dispute[]>('/api/disputes').then((d) => { setDisputes(d); setLoaded(true) })
    api.get<Inspection[]>('/api/inspections').then(setInsps)
  }
  useEffect(() => {
    load()
    const f = takeFocus('court')
    // A run handed over by the chatbot: a precheck goes to the precheck card, anything else to the case.
    if (f) api.get<{ kind: string }>(`/api/runs/${f}`).then((r) => (r.kind === 'precheck' ? setPreRun(f) : setRunId(f)))
  }, [])
  const run = useRun(runId, load)
  const d = disputes[0]
  const r = d?.result
  const evidence = useMemo(() => insps.flatMap((i) => i.evidence), [insps])

  const submit = async () => {
    if (!file) return setError(ko ? '공제 내역서 PDF를 선택하세요.' : 'Choose the deduction statement PDF.')
    const fd = new FormData()
    fd.append('file', file)
    Object.entries(form).forEach(([k, v]) => fd.append(k, v))
    try {
      setError(null)
      setRunId((await api.upload<{ run_id: number }>('/api/disputes', fd)).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const exhibits = (ids: number[]) =>
    ids.map((id) => evidence.find((e) => e.id === id)).filter(Boolean).map((e) => <EvidenceThumb key={e!.id} ev={e!} onOpen={setOpen} />)
  const late = Boolean(r?.facts.statement_late)

  return (
    <div>
      <PageHead title={ko ? '보증금' : 'Deposit'}
        sub={ko ? '집주인의 공제 내역을 항목별로 따지고 반환 요청 레터를 씁니다.' : 'Check every deduction and get a refund letter.'}
        agent="judge" color="#4f46e5"
        actions={d && (
          <>
            <a className="btn ghost small" href={fileUrl(d.deduction_file_id)} target="_blank" rel="noreferrer">{ko ? '집주인 내역서' : 'Landlord statement'}</a>
            <button className="btn ghost small" title={ko ? '다시 판정' : 'Run again'} disabled={run?.status === 'running'}
              onClick={async () => setRunId((await api.post<{ run_id: number }>(`/api/disputes/${d.id}/rerun`)).run_id)}>↻</button>
          </>
        )} />
      {run?.status === 'running' && <RunPanel run={run} compact />}

      {!loaded ? <div className="empty">…</div> : !r ? (
        <>
          <PrecheckCard onOpen={setOpen} focusRun={preRun} />
          <p className="small muted">⚖️ {ko ? '아직 공제 내역서가 없습니다. 퇴거 후 집주인 내역서가 오면 아래에서 사건을 여세요.' : 'No deduction statement yet. When it arrives after move-out, open a case below.'}</p>
        </>
      ) : (
        <>
          <div className="kpis">
            <Kpi label={ko ? '집주인 청구' : 'Landlord claimed'} value={money(r.money.claimed_total)} hint={`${ko ? '보증금' : 'deposit'} ${money(r.money.deposit)}`} />
            <Kpi label={ko ? '인정할 금액' : 'Fair deductions'} value={money(r.money.approved_total)} hint={ko ? '대법관 판결' : 'Chief Justice ruling'} />
            <Kpi label={ko ? '돌려받을 금액' : 'Refund to ask for'} value={money(r.money.refund_requested)} tone="good" hint={`${ko ? '이자 포함' : 'incl. interest'} ${money(r.money.interest)}`} />
            <Kpi label={ko ? '법정 기한' : 'Legal deadline'} value={fmtDate(String(r.facts.return_deadline), lang)} tone={late ? 'bad' : 'plain'}
              hint={late ? (ko ? `${r.facts.days_late}일 늦게 도착` : `arrived ${r.facts.days_late} days late`) : (ko ? '기한 내' : 'on time')} />
          </div>
          {late && (
            <div className="alert-row bad">⚠️ {ko ? `기한 위반 — 법상 보증금 2배(${money(r.money.statute_double_damages)}) 청구 가능성. 전문가 확인 필요.` : `Deadline missed — the landlord may owe twice the deposit (${money(r.money.statute_double_damages)}). Confirm with a lawyer.`}</div>
          )}
          {r.officer.hidden_removed.length > 0 && (
            <Disclosure summary={<>🛂 {ko ? '검문소가 내역서의 숨은 지시문을 제거했습니다' : 'The checkpoint removed hidden instructions from the statement'}</>}>
              {r.officer.hidden_removed.map((h, i) => <div key={i} className="mono small">“{h}”</div>)}
            </Disclosure>
          )}

          <Card title={ko ? '항목별 판정' : 'Item by item'}>
            {r.brief.items.map((b, i) => {
              const rule = r.ruling.items.find((x) => x.item.trim().toLowerCase() === b.item.trim().toLowerCase())
              return (
                <RowItem key={i}
                  main={b.item}
                  sub={`${ko ? '청구' : 'claimed'} ${money(b.amount_claimed)} → ${ko ? '판결' : 'ruled'} ${money(rule?.approved_deduction)}`}
                  right={<Pill tone={VERDICT_TONE[b.verdict]}>{VERDICT_LABEL[b.verdict][ko ? 1 : 0]}</Pill>}>
                  <p className="small">{pick(b as unknown as Record<string, unknown>, 'reason', lang)}</p>
                  {rule && <p className="small muted">⚖️ {ko ? rule.note_ko : rule.note_en}</p>}
                  <div className="exhibits">{exhibits(b.evidence_ids)}</div>
                  <div>{b.lease_pages.map((p) => <Pill key={p} tone="gray">lease p.{p}</Pill>)} {b.law_ids.map((l) => <Pill key={l} tone="purple">{l}</Pill>)}</div>
                </RowItem>
              )
            })}
          </Card>

          <Card>
            <Disclosure summary={`⚖️ ${ko ? '대법관 댄의 판결문' : 'Chief Justice Dan’s ruling'}`}>
              <p className="small">{pick(r.ruling as unknown as Record<string, unknown>, 'ruling', lang)}</p>
              {(ko ? r.brief.procedural_issues_ko : r.brief.procedural_issues_en).map((p, i) => <p key={i} className="small muted">• {p}</p>)}
            </Disclosure>
            <Disclosure summary={`✉️ ${ko ? '집주인에게 보낼 레터 (영어)' : 'Letter to the landlord'}`}
              right={<button className="btn ghost small" onClick={() => { navigator.clipboard.writeText(r.letter_en); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>{copied ? '✓' : (ko ? '복사' : 'Copy')}</button>}>
              {ko && <p className="small muted">{r.ruling.letter_ko_summary}</p>}
              <pre className="letter">{r.letter_en}</pre>
            </Disclosure>
          </Card>
        </>
      )}

      {r && <PrecheckCard onOpen={setOpen} compact focusRun={preRun} />}
      <Card>
        <Disclosure summary={`➕ ${ko ? '새 사건 열기 (공제 내역서 업로드)' : 'Open a new case (upload a deduction statement)'}`}>
          <div className="form-grid">
            <label>{ko ? '공제 내역서 PDF' : 'Deduction statement PDF'}<input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
            <label>{ko ? '입주 기록' : 'Move-in record'}
              <select value={form.move_in_id} onChange={(e) => setForm({ ...form, move_in_id: e.target.value })}>
                <option value="">—</option>
                {insps.filter((i) => i.kind === 'move_in').map((i) => <option key={i.id} value={i.id}>{kindLabel(i.kind, lang)} · {fmtDate(i.inspected_on, lang)}</option>)}
              </select>
            </label>
            <label>{ko ? '퇴거 기록' : 'Move-out record'}
              <select value={form.move_out_id} onChange={(e) => setForm({ ...form, move_out_id: e.target.value })}>
                <option value="">—</option>
                {insps.filter((i) => i.kind === 'move_out').map((i) => <option key={i.id} value={i.id}>{kindLabel(i.kind, lang)} · {fmtDate(i.inspected_on, lang)}</option>)}
              </select>
            </label>
            {([['termination_date', 'Tenancy ended', '계약 종료일'], ['forwarding_address_date', 'Forwarding address (in writing)', '새 주소 서면 통지일'], ['statement_received_date', 'Statement received', '내역서 받은 날'], ['keys_returned_date', 'Keys returned', '열쇠 반납일']] as const).map(([k, en, kk]) => (
              <label key={k}>{ko ? kk : en}<input type="date" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>
            ))}
          </div>
          <Err error={error} />
          <button className="btn primary small" onClick={submit} disabled={!form.move_in_id || !form.move_out_id}>⚖️ {ko ? '판정 시작' : 'Start'}</button>
        </Disclosure>
      </Card>
      <EvidenceModal ev={open} onClose={() => setOpen(null)} />
    </div>
  )
}
