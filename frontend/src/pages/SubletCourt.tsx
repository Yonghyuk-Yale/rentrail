/** Deposit Court for a subtenant: the escrow proposal, an appeal argued by Counsel Dan on the
 * subtenant's side, and the Chief Justice's new ruling. */

import { useEffect, useState } from 'react'
import { api, fmtDate, money, takeFocus } from '../api'
import RunPanel, { useRun } from '../components/RunPanel'
import { Card, Empty, Err, PageHead, Pill, Stat } from '../components/ui'
import { useApp } from '../i18n'

interface RulingItem { item: string; approved_deduction: number; hold_pending?: number; note_en: string; note_ko: string }
interface Settlement {
  held: number; interest: number; approved_deductions: number; pending?: number; to_sublessor: number; to_subtenant: number
  deadline: string | null; status: string; accepted_by: string[]; proposed_on: string; letter_en: string
  ruling: { items: RulingItem[]; ruling_en: string; ruling_ko: string }
  appeal?: { reason: string; on: string; brief: { items: { item: string; verdict: string; fair_amount: number; reason_en: string; reason_ko: string }[] } }
  history?: { to_subtenant: number; on: string }[]
}
interface SubletLite { id: number; role: string; status: string; end_date: string; deposit: number; escrow_balance: number; settlement: Settlement | null; return_deadline: string | null }

export default function SubletCourt() {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const [s, setS] = useState<SubletLite | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [reason, setReason] = useState('')
  const [runId, setRunId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = () => api.get<SubletLite[]>('/api/sublets').then((l) => { setS(l[0] ?? null); setLoaded(true) })
  useEffect(() => {
    load()
    const f = takeFocus('court')
    if (f) setRunId(f)
  }, [])
  const run = useRun(runId, load)
  const st = s?.settlement

  const appeal = async () => {
    setError(null)
    try {
      setRunId((await api.post<{ run_id: number }>(`/api/sublets/${s!.id}/appeal`, { reason })).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const accept = async () => {
    try {
      setS(await api.post<SubletLite>(`/api/sublets/${s!.id}/decision`, { decision: 'accept' }))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div>
      <PageHead title={ko ? '보증금 법정 (서브렛)' : 'Deposit Court (sublet)'}
        sub={ko ? '서브렛 보증금 정산에 이의가 있으면 변호사 댄이 내 편에서 다시 따집니다.' : 'Disagree with the escrow proposal? Counsel Dan argues it again on your side.'}
        agent="lawyer" color="#a855f7" />
      <Err error={error} />
      <RunPanel run={run} />
      {!loaded ? <div className="empty">…</div> : !s ? (
        <Empty>{ko ? '아직 서브렛이 없습니다.' : 'No sublet yet on this date.'}</Empty>
      ) : !st ? (
        <Empty>
          {ko ? `아직 정산 제안이 없습니다. 서브렛이 끝나는 ${fmtDate(s.end_date, lang)} 이후 반환 점검을 하면 제안이 나옵니다. 법정 반환 기한은 ${fmtDate(s.return_deadline, lang)}입니다.`
            : `No proposal yet. It comes after the return inspection on ${fmtDate(s.end_date, lang)}. The legal deadline is ${fmtDate(s.return_deadline, lang)}.`}
        </Empty>
      ) : (
        <>
          <Card title={ko ? '현재 정산안' : 'Current proposal'} right={<Pill tone={st.status === 'released' ? 'green' : 'amber'}>{st.status === 'released' ? (ko ? '지급 완료' : 'paid out') : (ko ? '제안' : 'proposed')} · {fmtDate(st.proposed_on, lang)}</Pill>}>
            <div className="stats money-row">
              <Stat label={ko ? '보관 중인 보증금' : 'Held in escrow'} value={money(st.held)} />
              <Stat label={ko ? '공제' : 'Deductions'} value={money(st.approved_deductions)} />
              {(st.pending ?? 0) > 0 && <Stat label={ko ? '영수증 대기 보류' : 'Held for an invoice'} value={money(st.pending)} />}
              <Stat label={ko ? '돌려받을 금액' : 'Back to you'} value={<span className="big ok">{money(st.to_subtenant)}</span>} hint={`${ko ? '이자 포함' : 'incl. interest'} ${money(st.interest)}`} />
              <Stat label={ko ? '법정 기한' : 'Legal deadline'} value={fmtDate(st.deadline, lang)} hint="CT §47a-21(d)(2)" />
            </div>
            <table className="tbl">
              <thead><tr><th>{ko ? '항목' : 'Item'}</th><th className="num">{ko ? '공제' : 'Deducted'}</th><th className="num">{ko ? '보류' : 'Held'}</th><th>{ko ? '이유' : 'Why'}</th></tr></thead>
              <tbody>
                {st.ruling.items.map((it, i) => (
                  <tr key={i}><td>{it.item}</td><td className="num">{money(it.approved_deduction)}</td><td className="num">{it.hold_pending ? money(it.hold_pending) : ''}</td><td className="small">{ko ? it.note_ko : it.note_en}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="small">{ko ? st.ruling.ruling_ko : st.ruling.ruling_en}</p>
            {st.history?.length ? <p className="small muted">{ko ? '이전 제안' : 'Earlier proposal'}: {st.history.map((h) => `${money(h.to_subtenant)} (${fmtDate(h.on, lang)})`).join(' → ')} → {money(st.to_subtenant)}</p> : null}
            {st.status !== 'released' && (
              <div className="row gap">
                <button className="btn primary" disabled={st.accepted_by.includes('subtenant')} onClick={accept}>✓ {ko ? '수락' : 'Accept'}</button>
                <span className="small muted">{ko ? '수락한 쪽' : 'Accepted by'}: {st.accepted_by.join(', ') || '—'}</span>
              </div>
            )}
          </Card>
          {st.appeal && (
            <Card title={`⚖️ ${ko ? '이의 제기 결과' : 'Appeal result'} · ${fmtDate(st.appeal.on, lang)}`}>
              <blockquote>“{st.appeal.reason}”</blockquote>
              <table className="tbl small-top">
                <thead><tr><th>{ko ? '항목' : 'Item'}</th><th>{ko ? '변호사 댄' : 'Counsel'}</th><th className="num">{ko ? '적정액' : 'Fair'}</th><th>{ko ? '근거' : 'Why'}</th></tr></thead>
                <tbody>
                  {st.appeal.brief.items.map((b, i) => (
                    <tr key={i}><td>{b.item}</td><td><Pill tone={b.verdict === 'contest' ? 'green' : b.verdict === 'partial' ? 'amber' : 'red'}>{b.verdict}</Pill></td><td className="num">{money(b.fair_amount)}</td><td className="small">{ko ? b.reason_ko : b.reason_en}</td></tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
          {st.status !== 'released' && (
            <Card title={ko ? '이의 제기' : 'Appeal'}>
              <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder={ko ? '예: 균열은 6월 2일 이미 있었고, 바로 서면으로 알렸습니다. 수리비 견적도 너무 높습니다.' : 'e.g. The crack was there on June 2 and I reported it in writing the same day; the repair estimate is too high.'} />
              <button className="btn primary small-top" disabled={run?.status === 'running'} onClick={appeal}>⚖️ {ko ? '변호사 댄에게 이의 제기 맡기기' : 'Have Counsel Dan appeal for me'}</button>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
