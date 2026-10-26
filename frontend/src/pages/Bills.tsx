/** Bills & insurance: three numbers, one row per bill (click for Treasurer Dan's notes and line
 * items), and, during a sublet, the utility shares. */

import { useEffect, useState } from 'react'
import { api, fileUrl, fmtDate, money } from '../api'
import RunPanel, { useRun } from '../components/RunPanel'
import UtilityShares from '../components/UtilityShares'
import { Card, Err, Kpi, PageHead, Pill, RowItem } from '../components/ui'
import { useApp } from '../i18n'

interface Note { en: string; ko: string; severity: 'info' | 'warn' | 'alert' }
interface Bill {
  id: number
  kind: 'bill' | 'policy'
  file_id: number
  file_name: string
  result: (Record<string, unknown> & { notes: Note[] }) | null
}

const toneOf = (n: Note) => (n.severity === 'alert' ? 'bad' : n.severity === 'warn' ? 'warn' : '')

export default function Bills() {
  const { lang, me } = useApp()
  const ko = lang === 'ko'
  const mode = me?.user.mode ?? 'tenant'
  const today = me?.today ?? ''
  const [bills, setBills] = useState<Bill[]>([])
  const [runId, setRunId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = () => api.get<Bill[]>('/api/bills').then(setBills)
  useEffect(() => {
    load()
  }, [])
  const run = useRun(runId, () => load())

  const upload = async (f: File | undefined, kind: string) => {
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    fd.append('kind', kind)
    try {
      setError(null)
      setRunId((await api.upload<{ run_id: number }>('/api/bills', fd)).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const utility = bills.filter((b) => b.kind === 'bill' && b.result)
  const upcoming = utility.filter((b) => String(b.result!.due_date ?? '') >= today)
  const dueSum = upcoming.reduce((a, b) => a + Number(b.result!.amount_due ?? 0), 0)
  const nextDue = upcoming.map((b) => String(b.result!.due_date)).sort()[0]
  const policy = bills.find((b) => b.kind === 'policy' && b.result)
  const p = policy?.result as Record<string, number | string | boolean | null> | undefined
  const notesOf = (b: Bill) => (b.result?.notes ?? []).map((n, i) => <div key={i} className={`alert-row ${toneOf(n)}`}>{ko ? n.ko : n.en}</div>)
  const pdf = (b: Bill) => <a className="btn ghost small" href={fileUrl(b.file_id)} target="_blank" rel="noreferrer">PDF</a>

  return (
    <div>
      <PageHead title={ko ? '공과금 · 보험' : 'Bills & insurance'}
        sub={ko ? '고지서와 보험을 계약서와 대조합니다. 줄을 누르면 자세히 보입니다.' : 'Bills and insurance, checked against your lease. Click a row for details.'}
        agent="treasurer" color="#22c55e"
        actions={
          <>
            {mode !== 'subtenant' && <label className="btn small">🧾 {ko ? '고지서' : 'Bill'}<input type="file" accept="application/pdf" hidden onChange={(e) => upload(e.target.files?.[0], 'bill')} /></label>}
            <label className="btn small">🛡️ {ko ? '보험 증권' : 'Policy'}<input type="file" accept="application/pdf" hidden onChange={(e) => upload(e.target.files?.[0], 'policy')} /></label>
          </>
        } />
      <Err error={error} />
      {run?.status === 'running' && <RunPanel run={run} compact />}

      <div className="kpis">
        {mode !== 'subtenant' && <Kpi label={ko ? '낼 공과금' : 'Bills to pay'} value={money(dueSum)} hint={ko ? `${upcoming.length}건` : `${upcoming.length} bill(s)`} />}
        {mode !== 'subtenant' && <Kpi label={ko ? '다음 납부일' : 'Next due'} value={nextDue ? fmtDate(nextDue, lang) : '—'} />}
        <Kpi label={ko ? '세입자 보험' : 'Renter’s insurance'}
          value={p ? (p.requirement_met ? (ko ? '요건 충족' : 'Meets lease') : p.requirement_met === false ? (ko ? '미달' : 'Below lease') : '—') : '—'}
          tone={p ? (p.requirement_met ? 'good' : 'bad') : 'plain'}
          hint={p ? `${money(p.liability_limit as number)} / ${ko ? '최소' : 'min'} ${money(p.lease_requirement as number)}` : (ko ? '증권을 올리세요' : 'upload your policy')} />
      </div>

      {mode !== 'tenant' && <UtilityShares />}

      <Card title={ko ? '서류' : 'Documents'}>
        {bills.length === 0 && <p className="muted small">{ko ? '이 날짜까지 도착한 서류가 없습니다.' : 'Nothing has arrived by this date.'}</p>}
        {bills.map((b) => {
          const r = b.result as Record<string, unknown> | null
          const notes = b.result?.notes ?? []
          const worst = notes.find((n) => n.severity === 'alert') ?? notes.find((n) => n.severity === 'warn')
          const period = r ? `${fmtDate(String(r.period_start ?? ''), lang)} → ${fmtDate(String(r.period_end ?? ''), lang)}` : (ko ? '읽는 중…' : 'reading…')
          if (b.kind === 'policy')
            return (
              <RowItem key={b.id} left="🛡️" tone={r?.requirement_met === false ? 'bad' : undefined}
                main={String(r?.insurer ?? b.file_name)}
                sub={r ? `${period} · ${ko ? '자기부담금' : 'deductible'} ${money(r.deductible as number)}` : period}
                right={r?.requirement_met === true ? <Pill tone="green">✓ {ko ? '충족' : 'OK'}</Pill> : r?.requirement_met === false ? <Pill tone="red">✗ {ko ? '미달' : 'Short'}</Pill> : undefined}>
                {notesOf(b)}
                {pdf(b)}
              </RowItem>
            )
          return (
            <RowItem key={b.id} left="🧾" tone={worst?.severity === 'alert' ? 'bad' : worst ? 'warn' : undefined}
              main={<>{String(r?.provider ?? b.file_name)} <span className="muted small">{String(r?.service ?? '')}</span></>}
              sub={r ? `${period} · ${ko ? '납부' : 'due'} ${fmtDate(String(r.due_date ?? ''), lang)}${worst ? ` · ⚠ ${ko ? worst.ko : worst.en}` : ''}` : period}
              right={<strong>{money(r?.amount_due as number)}</strong>}>
              {notesOf(b)}
              {r && (
                <>
                  <div>
                    {r.billed_by_landlord_or_billing_company ? <Pill tone="amber">{ko ? '관리회사/대행사 청구' : 'billed via landlord / billing company'}</Pill> : <Pill tone="blue">{ko ? '전력회사 직접 청구' : 'billed by the utility'}</Pill>}
                    {r.usage_value ? <Pill tone="gray">{`${r.usage_value} ${r.usage_unit ?? ''}`}</Pill> : null}
                    {r.supplier_contract_end ? <Pill tone="red">{ko ? '공급 계약 종료' : 'supplier contract ends'} {String(r.supplier_contract_end)}</Pill> : null}
                  </div>
                  <table className="tbl small-top">
                    <tbody>{((r.line_items as { label: string; amount: number }[]) ?? []).map((li, i) => <tr key={i}><td>{li.label}</td><td className="num">{money(li.amount)}</td></tr>)}</tbody>
                  </table>
                </>
              )}
              {pdf(b)}
            </RowItem>
          )
        })}
      </Card>
    </div>
  )
}
