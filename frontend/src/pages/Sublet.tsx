/** Sublet & escrow: who, how much is held, where it stands — then three tabs (money, documents,
 * settlement) whose details open on click. */

import { useEffect, useState } from 'react'
import { api, fileUrl, fmtDate, money, takeFocus } from '../api'
import Bulldog from '../components/Bulldog'
import RunPanel, { useRun } from '../components/RunPanel'
import { Card, Disclosure, Err, Kpi, Markdownish, PageHead, Pill, RowItem } from '../components/ui'
import { useApp } from '../i18n'
import type { Comparison, Inspection } from '../types'

interface Line { en: string; ko: string; law_id: string | null }
interface Settlement {
  held: number; interest: number; approved_deductions: number; to_sublessor: number; to_subtenant: number
  pending?: number; pending_items?: { item: string; amount: number; note_en: string; note_ko: string }[]
  invoice?: { amount: number; paid: number; returned: number; note: string }
  deadline: string | null; status: string; accepted_by: string[]; letter_en: string
  comparison: Comparison
  claim: { items: { item: string; amount: number; reason_en: string; reason_ko: string }[] }
  ruling: { items: { item: string; approved_deduction: number; note_en: string; note_ko: string; hold_pending?: number }[]; ruling_en: string; ruling_ko: string }
  utility_shares: { service: string; provider: string; period: string; amount: number; overlap_days: number; period_days: number; subtenant_share: number }[]
}
interface SubletT {
  id: number; role: 'sublessor' | 'subtenant'; status: string; invite_code: string | null
  start_date: string; end_date: string; monthly_rent: number; deposit: number; utilities: Record<string, string>
  owner_name: string; subtenant_name: string | null; escrow_balance: number; return_deadline: string | null
  handoff_id: number | null; return_id: number | null
  steps: { key: string; date: string | null }[]; today: string
  sublease: { id: number; file_id: number; signed_on: string; analysed: boolean; monthly_rent: number | null; utilities: { service: string; paid_by: string }[] } | null
  docs: { consent_letter_en: string; agreement_md_en: string; sublessor_duties: Line[]; subtenant_checklist: Line[]; risks: Line[]; summary_ko: string } | null
  settlement: Settlement | null
  ledger: { id: number; ts: string; kind: string; amount: number; from_party: string; to_party: string; method: string; masked_account: string; note: string }[]
}

const STEP_LABEL: Record<string, [string, string]> = {
  listed: ['Listed', '게시'], matched: ['Matched', '매칭'], deposit: ['Deposit in', '보증금 보관'],
  moved_in: ['Moved in', '입주'], returned: ['Returned', '반환'], settled: ['Settled', '정산'],
}
const STATUS_LABEL: Record<string, [string, string]> = {
  open: ['Looking for a subtenant', '세입자 찾는 중'], matched: ['Waiting for the deposit', '보증금 대기'],
  funded: ['Move-in ahead', '입주 예정'], active: ['Subtenant living there', '거주 중'],
  return_due: ['Ended — settle the deposit', '종료 — 정산 필요'], settlement_proposed: ['Settlement proposed', '정산안 제시'],
  disputed: ['Disputed', '이의 제기'], closed: ['Closed', '종료'],
}

export default function Sublet() {
  const { lang, go, me } = useApp()
  const ko = lang === 'ko'
  const [list, setList] = useState<SubletT[]>([])
  const [loaded, setLoaded] = useState(false)
  const [insps, setInsps] = useState<Inspection[]>([])
  const [runId, setRunId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [pay, setPay] = useState({ method: 'card', card_number: '4242 4242 4242 4242', routing: '', account: '' })
  const [tab, setTab] = useState<'escrow' | 'docs' | 'settle'>('escrow')
  const [inv, setInv] = useState({ amount: '', note: '' })
  const [invFile, setInvFile] = useState<File | null>(null)
  const [form, setForm] = useState({ start_date: '', end_date: '', monthly_rent: '', deposit: '', electricity: 'subtenant' })

  const load = () => {
    api.get<SubletT[]>('/api/sublets').then((l) => { setList(l); setLoaded(true) })
    api.get<Inspection[]>('/api/inspections').then(setInsps)
  }
  useEffect(() => {
    load()
    const f = takeFocus('sublet')
    if (f) setRunId(f)
  }, [])
  useEffect(() => {
    // Open the tab that matters at this point of the story.
    const st = list[0]?.status
    if (st && ['return_due', 'settlement_proposed', 'disputed', 'closed'].includes(st)) setTab('settle')
  }, [list[0]?.status])
  const run = useRun(runId, load)
  const s = list[0]

  const act = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const startRun = (path: string) => act(async () => setRunId((await api.post<{ run_id: number }>(path)).run_id))
  const lawPill = (l: Line) => l.law_id && <Pill tone="purple">{l.law_id}</Pill>

  const handoff = insps.find((i) => i.id === s?.handoff_id)
  const ret = insps.find((i) => i.id === s?.return_id)
  const st = s?.settlement

  return (
    <div>
      <PageHead title={ko ? '서브렛 · 에스크로' : 'Sublet & escrow'}
        sub={ko ? '서브렛 보증금은 Rentrail이 보관하고, 증거로 나눕니다. (결제는 시뮬레이션)' : 'Rentrail holds the sublet deposit and splits it by the evidence. (Simulated payments.)'}
        agent="sheriff" color="#eab308"
        actions={s && <Pill tone="blue">{(STATUS_LABEL[s.status] ?? [s.status, s.status])[ko ? 1 : 0]}</Pill>} />
      <Err error={error} />
      {run?.status === 'running' && <RunPanel run={run} compact />}

      {!loaded ? <div className="empty">…</div> : !s ? (
        me?.user.mode !== 'subtenant' ? (
          <Card title={ko ? '서브렛 내주기' : 'Sublet my place'}>
            <div className="form-grid">
              <label>{ko ? '시작' : 'Start'}<input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></label>
              <label>{ko ? '종료' : 'End'}<input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></label>
              <label>{ko ? '월세' : 'Monthly rent'}<input type="number" value={form.monthly_rent} onChange={(e) => setForm({ ...form, monthly_rent: e.target.value })} /></label>
              <label>{ko ? '서브렛 보증금' : 'Sublet deposit'}<input type="number" value={form.deposit} onChange={(e) => setForm({ ...form, deposit: e.target.value })} /></label>
              <label>{ko ? '전기요금' : 'Electricity paid by'}
                <select value={form.electricity} onChange={(e) => setForm({ ...form, electricity: e.target.value })}><option value="subtenant">subtenant</option><option value="sublessor">sublessor</option></select>
              </label>
            </div>
            <button className="btn primary" onClick={() => act(() => api.post('/api/sublets', { ...form, utilities: { electricity: form.electricity } }))}>{ko ? '서브렛 만들기' : 'Create sublet'}</button>
          </Card>
        ) : (
          <Card title={ko ? '초대 코드로 참여' : 'Join with an invite code'}>
            <div className="row gap">
              <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="DAN427" />
              <button className="btn primary" onClick={() => act(() => api.post('/api/sublets/join', { code }))}>{ko ? '참여' : 'Join'}</button>
            </div>
          </Card>
        )
      ) : (
        <>
          <div className="sublet-strip">
            <div className={`party ${s.role === 'sublessor' ? 'me' : ''}`}>
              <Bulldog costume="plain" furColor="#3b82f6" size={40} />
              <div><strong>{s.owner_name}</strong><div className="small muted">{ko ? '내주는 사람' : 'Sublessor'}</div></div>
            </div>
            <div className="escrow-mini">
              <Bulldog costume="sheriff" furColor="#eab308" size={44} />
              <div><div className="small muted">{ko ? '에스크로' : 'In escrow'}</div><div className="big">{money(s.escrow_balance)}</div></div>
            </div>
            <div className={`party ${s.role === 'subtenant' ? 'me' : ''}`}>
              <Bulldog costume="plain" furColor="#22c55e" size={40} />
              <div><strong>{s.subtenant_name ?? '—'}</strong><div className="small muted">{ko ? '서브렛 세입자' : 'Subtenant'}</div></div>
            </div>
          </div>

          <div className="kpis">
            <Kpi label={ko ? '기간' : 'Period'} value={fmtDate(s.start_date, lang)} hint={`→ ${fmtDate(s.end_date, lang)}`} />
            <Kpi label={ko ? '월세' : 'Rent'} value={money(s.monthly_rent)} />
            <Kpi label={ko ? '서브렛 보증금' : 'Deposit'} value={money(s.deposit)} hint={s.invite_code ? `${ko ? '초대 코드' : 'invite'} ${s.invite_code}` : undefined} />
            <Kpi label={ko ? '정산 기한' : 'Settle by'} value={fmtDate(s.return_deadline, lang)} hint="CT §47a-21" />
          </div>

          <ol className="hsteps">
            {s.steps.map((x) => (
              <li key={x.key} className={x.date ? 'done' : ''}>
                <span className="vdot">{x.date ? '✓' : ''}</span>
                <span>{STEP_LABEL[x.key]?.[ko ? 1 : 0] ?? x.key}</span>
                <span className="muted small">{x.date ? fmtDate(x.date, lang) : ''}</span>
              </li>
            ))}
          </ol>

          <div className="tabs">
            <button className={tab === 'escrow' ? 'on' : ''} onClick={() => setTab('escrow')}>💳 {ko ? '돈 · 장부' : 'Money'}</button>
            <button className={tab === 'docs' ? 'on' : ''} onClick={() => setTab('docs')}>📝 {ko ? '서류' : 'Documents'}</button>
            <button className={tab === 'settle' ? 'on' : ''} onClick={() => setTab('settle')}>⚖️ {ko ? '정산' : 'Settlement'}</button>
          </div>

          {tab === 'escrow' && (
            <>
              {s.role === 'subtenant' && (
                <Card title={ko ? '가상 결제' : 'Simulated payment'}>
                  <div className="row gap">
                    <div className="tabs small">
                      <button className={pay.method === 'card' ? 'on' : ''} onClick={() => setPay({ ...pay, method: 'card' })}>{ko ? '카드' : 'Card'}</button>
                      <button className={pay.method === 'ach' ? 'on' : ''} onClick={() => setPay({ ...pay, method: 'ach' })}>ACH</button>
                    </div>
                    {pay.method === 'card' ? (
                      <input value={pay.card_number} onChange={(e) => setPay({ ...pay, card_number: e.target.value })} aria-label="card" />
                    ) : (
                      <>
                        <input value={pay.routing} placeholder="Routing 011000015" onChange={(e) => setPay({ ...pay, routing: e.target.value })} />
                        <input value={pay.account} placeholder="Account 000123456789" onChange={(e) => setPay({ ...pay, account: e.target.value })} />
                      </>
                    )}
                  </div>
                  <div className="row gap">
                    <button className="btn primary" disabled={s.escrow_balance > 0} onClick={() => act(() => api.post(`/api/sublets/${s.id}/pay-deposit`, pay))}>
                      {ko ? `보증금 ${money(s.deposit)} 맡기기` : `Put ${money(s.deposit)} in escrow`}
                    </button>
                    <button className="btn" onClick={() => act(() => api.post(`/api/sublets/${s.id}/pay-rent`, { ...pay, note: `Rent for ${me?.today}` }))}>
                      {ko ? `월세 ${money(s.monthly_rent)} 보내기` : `Pay ${money(s.monthly_rent)} rent`}
                    </button>
                    <span className="small muted">{ko ? '카드는 끝 4자리만 저장' : 'Only the last 4 digits are kept'}</span>
                  </div>
                </Card>
              )}
              <Card title={ko ? '에스크로 장부' : 'Escrow ledger'} right={
                <button className="btn ghost small" onClick={() => window.confirm(ko ? '장부와 정산을 지우고 매칭 직후 상태로 되돌릴까요? (데모용)' : 'Clear the ledger and settlement and go back to just-matched? (demo)') && act(() => api.post(`/api/sublets/${s.id}/reset`))}>
                  ↺ {ko ? '초기화' : 'Reset'}
                </button>}>
                {s.ledger.length === 0 ? <p className="muted small">{ko ? '아직 기록이 없습니다.' : 'No entries yet.'}</p> : (
                  <table className="tbl">
                    <thead><tr><th>{ko ? '날짜' : 'Date'}</th><th>{ko ? '종류' : 'Type'}</th><th>{ko ? '흐름' : 'Flow'}</th><th className="num">{ko ? '금액' : 'Amount'}</th></tr></thead>
                    <tbody>
                      {s.ledger.map((l) => (
                        <tr key={l.id} title={`${l.note} · ${l.method} ${l.masked_account}`}>
                          <td className="nowrap">{fmtDate(l.ts.slice(0, 10), lang)}</td>
                          <td><Pill tone={l.kind === 'refund' ? 'green' : l.kind === 'payout' ? 'amber' : l.kind === 'notice' ? 'gray' : 'blue'}>{l.kind}</Pill></td>
                          <td className="small">{l.from_party} → {l.to_party}</td>
                          <td className="num">{l.amount ? money(l.amount) : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </>
          )}

          {tab === 'docs' && (
            <Card>
              <RowItem left="📝" main={ko ? '서브렛 계약서' : 'Sublease'}
                sub={s.sublease ? `${ko ? '서명' : 'signed'} ${fmtDate(s.sublease.signed_on, lang)} · ${money(s.sublease.monthly_rent)}/${ko ? '월' : 'mo'}` : (ko ? '아직 서명 전 (데모: 2027-05-10)' : 'not signed yet (demo: 2027-05-10)')}
                right={s.sublease && <a className="btn ghost small" href={fileUrl(s.sublease.file_id)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>PDF</a>}>
                {s.sublease && <button className="btn small" onClick={() => { sessionStorage.setItem('rentrail_lease_tab', 'sublease'); go('lease') }}>{ko ? '계약서 요약 보기' : 'Open the summary'} →</button>}
              </RowItem>
              {!s.docs ? (
                <div className="row gap small-top">
                  <span className="muted small">{ko ? '보안관 댄이 동의 요청서·계약서 초안·체크리스트를 씁니다.' : 'Sheriff Dan drafts the consent letter, agreement and checklist.'}</span>
                  <button className="btn primary small" onClick={() => startRun(`/api/sublets/${s.id}/docs`)} disabled={run?.status === 'running'}>📝 {ko ? '작성' : 'Draft'}</button>
                </div>
              ) : (
                <>
                  <Disclosure defaultOpen count={(s.role === 'sublessor' ? s.docs.sublessor_duties : s.docs.subtenant_checklist).length}
                    summary={`✅ ${s.role === 'sublessor' ? (ko ? '내 의무 (CT 법)' : 'My duties (CT law)') : (ko ? '입주 전 체크리스트' : 'Before you move in')}`}>
                    <ul className="lines">{(s.role === 'sublessor' ? s.docs.sublessor_duties : s.docs.subtenant_checklist).map((l, i) => <li key={i}>{ko ? l.ko : l.en} {lawPill(l)}</li>)}</ul>
                  </Disclosure>
                  <Disclosure summary={`⚠️ ${ko ? '위험 요소' : 'Risks'}`} count={s.docs.risks.length}>
                    <ul className="lines">{s.docs.risks.map((l, i) => <li key={i}>{ko ? l.ko : l.en} {lawPill(l)}</li>)}</ul>
                  </Disclosure>
                  <Disclosure summary={`✉️ ${ko ? '집주인 동의 요청 레터 (영어)' : 'Landlord consent request'}`}>
                    <pre className="letter">{s.docs.consent_letter_en}</pre>
                  </Disclosure>
                  <Disclosure summary={`📄 ${ko ? '서브렛 계약서 초안 (영어)' : 'Sublease agreement draft'}`}>
                    {ko && <p className="small muted">{s.docs.summary_ko}</p>}
                    <Markdownish text={s.docs.agreement_md_en} />
                  </Disclosure>
                  <div className="row gap small-top">
                    <button className="btn ghost small" onClick={() => startRun(`/api/sublets/${s.id}/docs`)} disabled={run?.status === 'running'}>↻ {ko ? '다시 작성' : 'Draft again'}</button>
                  </div>
                </>
              )}
            </Card>
          )}

          {tab === 'settle' && (
            <>
              <Card title={ko ? '점검 기록' : 'Inspections'}>
                {([['sublet_handoff', handoff, ko ? '인계 (입주 전)' : 'Hand-off'], ['sublet_return', ret, ko ? '반환 (퇴거 시)' : 'Return']] as const).map(([kind, insp, label]) => (
                  <div key={kind} className="rowitem">
                    <div className="rowitem-head static">
                      <span className="rowitem-left">{insp ? '📷' : '○'}</span>
                      <span className="rowitem-main">
                        <span className="rowitem-title">{label}</span>
                        <span className="rowitem-sub">{insp ? `${fmtDate(insp.inspected_on, lang)} · ${insp.evidence.length} ${ko ? '개 증거' : 'files'} · ${insp.result ? `${insp.result.findings.length} ${ko ? '개 하자' : 'defects'}` : (ko ? '분석 전' : 'not analysed')}` : (ko ? '아직 없음' : 'not yet')}</span>
                      </span>
                      <span className="rowitem-right">
                        {insp
                          ? <button className="btn ghost small" onClick={() => go('inspections')}>{ko ? '열기' : 'Open'} →</button>
                          : <button className="btn small" onClick={() => act(() => api.post('/api/inspections', { kind, sublet_id: s.id }))}>+ {ko ? '만들기' : 'Create'}</button>}
                      </span>
                    </div>
                  </div>
                ))}
                <div className="row gap small-top">
                  <button className="btn primary" disabled={run?.status === 'running' || !s.escrow_balance || !['return_due', 'settlement_proposed', 'disputed'].includes(s.status)} onClick={() => startRun(`/api/sublets/${s.id}/settle`)}>
                    ⚖️ {st ? (ko ? '정산 다시 받기' : 'Settle again') : (ko ? '정산 판결 받기' : 'Get a settlement ruling')}
                  </button>
                  {!st && <span className="small muted">{ko ? '서브렛이 끝나면 열립니다' : 'Opens when the sublet ends'}</span>}
                </div>
              </Card>

              {st && (
                <>
                  <div className="kpis">
                    <Kpi label={ko ? '보관액 + 이자' : 'Held + interest'} value={money(st.held + st.interest)} hint={`${ko ? '이자' : 'interest'} ${money(st.interest)} (0.49%)`} />
                    <Kpi label={ko ? '공제' : 'Deductions'} value={money(st.approved_deductions)} tone="warn" hint={(st.pending ?? 0) > 0 ? `${ko ? '영수증 대기' : 'held for invoice'} ${money(st.pending)}` : undefined} />
                    <Kpi label={ko ? '내주는 사람에게' : 'To sublessor'} value={money(st.to_sublessor)} />
                    <Kpi label={ko ? '세입자에게 반환' : 'Back to subtenant'} value={money(st.to_subtenant)} tone="good" />
                  </div>

                  <Card title={ko ? '항목별 판정' : 'Item by item'} right={<Pill tone={st.status === 'released' ? 'green' : st.status === 'disputed' ? 'red' : 'amber'}>{({ proposed: ['Proposed', '제안됨'], released: ['Paid out', '지급 완료'], disputed: ['Disputed', '이의 제기'] } as Record<string, string[]>)[st.status]?.[ko ? 1 : 0] ?? st.status}</Pill>}>
                    {st.ruling.items.map((it, i) => {
                      // Utility lines carry the code's proration formula instead of a second row.
                      const u = st.utility_shares.find((x) => it.item.toLowerCase().includes(x.service.toLowerCase()))
                      return (
                        <RowItem key={i} left={u ? '🔌' : '🔧'} main={it.item}
                          sub={it.hold_pending
                            ? `${ko ? '보류' : 'held'} ${money(it.hold_pending)} — ${ko ? '수리 영수증이 오면 정산' : 'paid when a repair invoice arrives'}`
                            : u ? `${u.provider} ${u.period}: ${money(u.amount)} × ${u.overlap_days}/${u.period_days} ${ko ? '일' : 'days'}` : undefined}
                          right={<strong>{money(it.approved_deduction)}</strong>}>
                          <p className="small">{ko ? it.note_ko : it.note_en}</p>
                        </RowItem>
                      )
                    })}
                    <Disclosure summary={`⚖️ ${ko ? '판결문' : 'Ruling'}`}>
                      <p className="small">{ko ? st.ruling.ruling_ko : st.ruling.ruling_en}</p>
                    </Disclosure>
                    <Disclosure summary={`✉️ ${ko ? '양쪽에 보내는 정산 통지 (영어)' : 'Settlement notice to both parties'}`}>
                      <pre className="letter">{st.letter_en}</pre>
                    </Disclosure>
                    <div className="row gap small-top">
                      <button className="btn primary" disabled={st.status === 'released' || st.accepted_by.includes(s.role)} onClick={() => act(() => api.post(`/api/sublets/${s.id}/decision`, { decision: 'accept' }))}>
                        ✓ {ko ? '수락' : 'Accept'}
                      </button>
                      {s.role === 'subtenant' && st.status !== 'released' && (
                        <button className="btn ghost" onClick={() => go('court')}>{ko ? '이의 제기 →' : 'Appeal →'}</button>
                      )}
                      <span className="small muted">{ko ? '수락' : 'Accepted'}: {st.accepted_by.join(', ') || '—'} · {ko ? '양쪽 수락 시 지급' : 'pays out when both accept'}</span>
                    </div>
                  </Card>

                  {st.invoice && <div className="alert-row">🧾 {ko ? '영수증 정산' : 'Invoice settled'}: {money(st.invoice.paid)} → sublessor, {money(st.invoice.returned)} → subtenant ({st.invoice.note})</div>}
                  {s.role === 'sublessor' && st.status === 'released' && (st.pending ?? 0) > 0 && (
                    <Card>
                      <Disclosure summary={`🧾 ${ko ? `수리 영수증 올리기 (보류 ${money(st.pending)})` : `Upload the repair invoice (hold ${money(st.pending)})`}`}>
                        <div className="form-grid">
                          <label>{ko ? '실제 수리비' : 'Actual repair cost'}<input type="number" value={inv.amount} onChange={(e) => setInv({ ...inv, amount: e.target.value })} /></label>
                          <label>{ko ? '메모' : 'Note'}<input value={inv.note} onChange={(e) => setInv({ ...inv, note: e.target.value })} placeholder="Painter invoice #123" /></label>
                          <label>{ko ? '영수증 파일 (선택)' : 'Invoice file (optional)'}<input type="file" onChange={(e) => setInvFile(e.target.files?.[0] ?? null)} /></label>
                        </div>
                        <button className="btn primary small" onClick={() => act(async () => { const fd = new FormData(); fd.append('amount', inv.amount || '0'); fd.append('note', inv.note); if (invFile) fd.append('file', invFile); await api.upload(`/api/sublets/${s.id}/invoice`, fd) })}>
                          {ko ? '제출' : 'Submit'}
                        </button>
                        <p className="small muted">{ko ? '영수증 금액만 지급되고 나머지는 세입자에게 돌아갑니다.' : 'Only the invoiced part is paid; the rest goes back to the subtenant.'}</p>
                      </Disclosure>
                    </Card>
                  )}
                </>
              )}
            </>
          )}
          <Disclosure summary={<span className="small muted">⚖️ CT §47a-21(a)(7) — {ko ? '서브렛을 내준 세입자도 법적으로 집주인입니다 (21일 반환·항목별 내역·이자)' : 'a tenant who sublets is a landlord under CT deposit law (21 days, itemized, interest)'}</span>}>
            <p className="small muted">{ko ? 'Rentrail은 이 의무를 대신 지키도록 기한과 금액을 코드로 계산합니다.' : 'Rentrail computes those deadlines and amounts in code so the sublessor meets them.'}</p>
          </Disclosure>
        </>
      )}
    </div>
  )
}
