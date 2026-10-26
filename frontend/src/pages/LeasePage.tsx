/** Lease (or sublease): the essentials as tiles, every deadline in one table, clauses one click away. */

import { useEffect, useState } from 'react'
import { api, fileUrl, fmtDate, money } from '../api'
import RunPanel, { useRun } from '../components/RunPanel'
import { Card, Disclosure, Empty, Err, Kpi, PageHead, Pill, RowItem } from '../components/ui'
import { pick, useApp } from '../i18n'
import type { Lease, Task } from '../types'
import { DeadlineTable } from './Home'

export default function LeasePage() {
  const { lang, me } = useApp()
  const ko = lang === 'ko'
  const mode = me?.user.mode ?? 'tenant'
  const [kind, setKind] = useState<'' | 'sublease'>(() => {
    const k = sessionStorage.getItem('rentrail_lease_tab')
    sessionStorage.removeItem('rentrail_lease_tab')
    return k === 'sublease' ? 'sublease' : ''
  })
  const [ownsSublet, setOwnsSublet] = useState(false)
  const [lease, setLease] = useState<Lease | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [tasks, setTasks] = useState<Task[]>([])
  const [runId, setRunId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [allClauses, setAllClauses] = useState(false)

  const load = () => {
    api.get<{ lease: Lease | null }>(`/api/leases/current${kind ? '?kind=sublease' : ''}`).then((r) => { setLease(r.lease); setLoaded(true) })
    api.get<{ tasks: Task[] }>('/api/calendar').then((r) => setTasks(r.tasks))
  }
  useEffect(load, [kind])
  useEffect(() => {
    api.get<{ role: string }[]>('/api/sublets').then((l) => setOwnsSublet(l.some((x) => x.role === 'sublessor')))
  }, [])
  const run = useRun(runId, load)

  const upload = async (f: File | undefined) => {
    if (!f) return
    setError(null)
    const fd = new FormData()
    fd.append('file', f)
    try {
      let path = '/api/leases'
      if (mode === 'subtenant' || kind === 'sublease') {
        const subs = await api.get<{ id: number }[]>('/api/sublets')
        if (!subs.length) throw new Error(ko ? '아직 서브렛이 없습니다.' : 'No sublet yet on this date.')
        path = `/api/sublets/${subs[0].id}/sublease`
      }
      setRunId((await api.upload<{ run_id: number }>(path, fd)).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const toggle = async (key: string) => {
    await api.post(`/api/tasks/${encodeURIComponent(key)}/toggle`)
    load()
  }

  const card = lease?.card
  const isSub = mode === 'subtenant' || kind === 'sublease'
  const clauses = (card?.clauses ?? []).filter((c) => allClauses || c.importance === 'high')
  const firstSentence = card ? pick(card as unknown as Record<string, unknown>, 'summary', lang).split(/(?<=[.。다])\s/)[0] : ''

  return (
    <div>
      <PageHead
        title={isSub ? (ko ? '서브렛 계약서' : 'Sublease') : (ko ? '계약서' : 'Lease')}
        sub={ko ? '서기관 댄이 정리한 핵심만. 조항을 누르면 원문이 보입니다.' : 'The essentials from Clerk Dan. Click a clause for the original wording.'}
        agent="clerk" color="#3b82f6"
        actions={
          <>
            {lease && <a className="btn ghost small" href={fileUrl(lease.file_id)} target="_blank" rel="noreferrer">PDF ({lease.page_count ?? '?'}p)</a>}
            {lease && <button className="btn ghost small" title={ko ? '다시 분석' : 'Analyse again'} onClick={async () => setRunId((await api.post<{ run_id: number }>(`/api/leases/${lease.id}/analyze`)).run_id)}>↻</button>}
            <label className="btn small">{ko ? '업로드' : 'Upload'}<input type="file" accept="application/pdf" hidden onChange={(e) => upload(e.target.files?.[0])} /></label>
          </>
        }
      />
      {mode !== 'subtenant' && (ownsSublet || mode === 'sublessor') && (
        <div className="tabs">
          <button className={kind === '' ? 'on' : ''} onClick={() => setKind('')}>{ko ? '원 임대 계약서' : 'Master lease'}</button>
          <button className={kind === 'sublease' ? 'on' : ''} onClick={() => setKind('sublease')}>{ko ? '서브렛 계약서' : 'Sublease'}</button>
        </div>
      )}
      <Err error={error} />
      {run?.status === 'running' && <RunPanel run={run} compact />}

      {!loaded ? <div className="empty">…</div> : !card ? (
        <Empty>
          {isSub
            ? (ko ? '이 날짜에는 아직 체결된 서브렛 계약서가 없습니다. (데모: 2027년 5월 10일 체결)' : 'No signed sublease on this date yet. (Demo: signed May 10, 2027.)')
            : (ko ? '계약서 PDF를 올리면 서기관 댄이 정리합니다.' : 'Upload your lease PDF and Clerk Dan will summarise it.')}
        </Empty>
      ) : (
        <>
          <p className="lead-line">{firstSentence}</p>
          <div className="kpis six">
            <Kpi label={ko ? '기간' : 'Term'} value={`${fmtDate(card.lease_start, lang)}`} hint={`→ ${fmtDate(card.lease_end, lang)}${card.auto_renews ? (ko ? ' · 자동 갱신' : ' · auto-renews') : ''}`} />
            <Kpi label={ko ? '월세' : 'Rent'} value={money(card.monthly_rent)} hint={card.rent_due_day ? (ko ? `매월 ${card.rent_due_day}일` : `due on day ${card.rent_due_day}`) : ''} />
            <Kpi label={ko ? '보증금' : 'Deposit'} value={money(card.security_deposit)} />
            {!isSub && <Kpi label={ko ? '입주 점검표' : 'Condition form'} value={card.inventory_form_hours ? `${card.inventory_form_hours}h` : '—'} hint={ko ? '입주 후 제출' : 'after move-in'} tone="warn" />}
            {!isSub && <Kpi label={ko ? '퇴거 통지' : 'Move-out notice'} value={card.move_out_notice_days ? `${card.move_out_notice_days}${ko ? '일 전' : ' days'}` : '—'} />}
            <Kpi label={ko ? '배상책임 보험' : 'Liability insurance'} value={card.insurance_min_liability ? money(card.insurance_min_liability) : '—'} hint={ko ? '최소' : 'minimum'} />
          </div>

          {!isSub && (
            <Card title={ko ? '일정' : 'Deadlines'}>
              <DeadlineTable tasks={tasks.filter((t) => t.days_left === null || t.days_left >= -14)} onToggle={toggle} />
              {tasks.some((t) => t.days_left !== null && t.days_left < -14) && (
                <Disclosure summary={<span className="small muted">{ko ? '지난 일정' : 'Past deadlines'}</span>} count={tasks.filter((t) => t.days_left !== null && t.days_left < -14).length}>
                  <DeadlineTable tasks={tasks.filter((t) => t.days_left !== null && t.days_left < -14)} onToggle={toggle} />
                </Disclosure>
              )}
            </Card>
          )}

          <Card>
            <Disclosure summary={`🚩 ${ko ? '주의할 조항' : 'Terms to watch'}`} count={card.red_flags.length} defaultOpen>
              {card.red_flags.map((r, i) => (
                <RowItem key={i} main={pick(r as unknown as Record<string, unknown>, 'title', lang)} right={r.page ? <Pill tone="gray">p.{r.page}</Pill> : undefined}>
                  <p className="small">{pick(r as unknown as Record<string, unknown>, 'why', lang)}</p>
                </RowItem>
              ))}
            </Disclosure>
            <Disclosure summary={`📜 ${ko ? '핵심 조항' : 'Key clauses'}`} count={card.clauses.length}
              right={<button className="btn ghost small" onClick={() => setAllClauses(!allClauses)}>{allClauses ? (ko ? '중요만' : 'Important') : (ko ? '전체' : 'All')}</button>}>
              {clauses.map((c, i) => (
                <RowItem key={i} main={pick(c as unknown as Record<string, unknown>, 'title', lang)} right={<Pill tone="gray">p.{c.page ?? '?'}</Pill>}>
                  <p className="small">{pick(c as unknown as Record<string, unknown>, 'plain', lang)}</p>
                  <blockquote>“{c.quote}”</blockquote>
                </RowItem>
              ))}
            </Disclosure>
            <Disclosure summary={`💡 ${ko ? '공과금: 누가 내고 누가 청구하나' : 'Utilities: who pays, who bills'}`} count={card.utilities.length}>
              <table className="tbl">
                <tbody>
                  {card.utilities.map((u, i) => (
                    <tr key={i}><td>{u.service}</td><td><Pill tone={u.paid_by === 'tenant' ? 'amber' : 'gray'}>{u.paid_by}</Pill></td><td className="small muted">{u.billed_by}</td><td className="small muted">{u.page ? `p.${u.page}` : ''}</td></tr>
                  ))}
                </tbody>
              </table>
            </Disclosure>
          </Card>
          <p className="small muted">💬 {ko ? '계약서에 대해 궁금한 점은 오른쪽 아래 대법관 댄에게 물어보세요.' : 'Questions about the lease? Ask Chief Justice Dan (bottom right).'}</p>
        </>
      )}
    </div>
  )
}
