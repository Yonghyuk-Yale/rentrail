import { useEffect, useMemo, useState } from 'react'
import { api, fmtDate, num, usd } from '../api'
import Bulldog from '../components/Bulldog'
import RunPanel, { AgentChip, useRun } from '../components/RunPanel'
import { Card, PageHead, Pill, Stat } from '../components/ui'
import { useApp } from '../i18n'
import type { Run } from '../types'

interface Tokens {
  by_agent: { agent: string; calls: number; input_tokens: number; cached_tokens: number; output_tokens: number; cost_usd: number; avg_ms: number }[]
  by_kind: { kind: string; runs: number; avg_input: number; avg_cached: number; avg_output: number; avg_cost: number; total_cost: number }[]
  total: { runs: number; input_tokens: number; cached_tokens: number; output_tokens: number; cost_usd: number }
  price: { input: number; cached_input: number; output: number }
  model: string
  limits: { run: number; daily: number }
  tokens_today: number
}

/** Typical runs per renter per month (assumption shown in the UI and the report). */
const USAGE: Record<string, [number, string, string]> = {
  lease: [1 / 12, 'Lease analysis (once a year)', '계약서 분석 (1년 1회)'],
  inspection: [4 / 12, 'Inspections (4 a year)', '점검 (1년 4회)'],
  compare: [1 / 12, 'Before/after compare', '전후 비교'],
  deposit_case: [1 / 12, 'Deposit case (once at move-out)', '보증금 사건 (퇴거 때 1회)'],
  bill: [2, 'Bills read (2 a month)', '고지서 (월 2건)'],
  policy: [1 / 12, 'Insurance policy (once a year)', '보험 증권 (1년 1회)'],
  chat: [6, 'Copilot questions (6 a month)', '코파일럿 질문 (월 6회)'],
  sublet_docs: [0.3 / 12, 'Sublet documents (30% of renters)', '서브렛 서류 (30%)'],
  sublet_settle: [0.3 / 12, 'Sublet settlement (30% of renters)', '서브렛 정산 (30%)'],
  community: [0.5, 'Community answers', '커뮤니티 답변'],
  lease_question: [1, 'Lease questions', '계약서 질문'],
}

const FLOW: { id: string; x: number; y: number }[] = [
  { id: 'user', x: -10, y: 120 },
  { id: 'officer', x: 110, y: 120 },
  { id: 'chief_justice', x: 300, y: 120 },
  { id: 'clerk', x: 520, y: 20 },
  { id: 'detective', x: 560, y: 95 },
  { id: 'counsel', x: 560, y: 170 },
  { id: 'sheriff', x: 520, y: 245 },
  { id: 'treasurer', x: 300, y: 260 },
]

export default function AgentRoom() {
  const { lang, roster } = useApp()
  const ko = lang === 'ko'
  const [tokens, setTokens] = useState<Tokens | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [sel, setSel] = useState<number | null>(null)
  useEffect(() => {
    api.get<Tokens>('/api/tokens').then(setTokens)
    api.get<Run[]>('/api/runs').then((r) => {
      setRuns(r)
      const firstCase = r.find((x) => x.kind === 'deposit_case' && x.status === 'done') ?? r[0]
      if (firstCase) setSel(firstCase.id)
    })
  }, [])
  const run = useRun(sel)

  const maxCost = Math.max(...(tokens?.by_agent.map((a) => a.cost_usd) ?? [0]), 1e-9)
  const perUser = useMemo(() => {
    if (!tokens) return { cost: 0, rows: [] as { kind: string; n: number; c: number }[] }
    const rows = tokens.by_kind.filter((k) => USAGE[k.kind]).map((k) => ({ kind: k.kind, n: USAGE[k.kind][0], c: USAGE[k.kind][0] * k.avg_cost }))
    return { cost: rows.reduce((s, r) => s + r.c, 0), rows }
  }, [tokens])
  const cacheShare = tokens && tokens.total.input_tokens ? tokens.total.cached_tokens / tokens.total.input_tokens : 0

  return (
    <div>
      <PageHead
        title={ko ? '에이전트 룸' : 'Agent Room'}
        sub={ko ? '에이전트끼리 주고받은 내용과 토큰 사용량.' : 'What the agents said to each other, and what it cost.'}
        agent="judge"
        color="#4f46e5"
      />

      <Card title={ko ? '흐름: 사용자 → 검문소 → 보스 → 전문가' : 'Flow: you → Checkpoint → Boss → specialists'}>
        <div className="flow">
          <svg viewBox="0 0 680 320" className="flow-svg" aria-hidden="true">
            {FLOW.filter((f) => !['officer', 'chief_justice'].includes(f.id)).map((f) => (
              <line key={f.id} x1={340} y1={150} x2={f.x + 40} y2={f.y + 30} stroke="#94a3b8" strokeWidth="2" strokeDasharray="5 4" />
            ))}
            <line x1={40} y1={150} x2={300} y2={150} stroke="#ef4444" strokeWidth="3" />
            
          </svg>
          {FLOW.map((f) => {
            if (f.id === 'user')
              return (
                <div key={f.id} className="flow-node" style={{ left: `${(f.x / 680) * 100}%`, top: `${(f.y / 320) * 100}%` }}>
                  <div className="flow-user">👤</div>
                  <div className="small"><strong>{ko ? '사용자' : 'You'}</strong><div className="muted">{ko ? '사진·영상·PDF·질문' : 'photos, video, PDFs, questions'}</div></div>
                </div>
              )
            const a = roster.find((r) => r.id === f.id)
            if (!a) return null
            return (
              <div key={f.id} className={`flow-node ${f.id === 'chief_justice' ? 'boss' : ''}`} style={{ left: `${(f.x / 680) * 100}%`, top: `${(f.y / 320) * 100}%` }}>
                <Bulldog costume={a.costume} furColor={a.color} size={f.id === 'chief_justice' ? 64 : f.id === 'officer' ? 60 : 48} />
                <div className="small"><strong>{ko ? a.name_ko : a.name}</strong>{f.id === 'officer' && <div className="muted">{ko ? '모든 입력이 먼저 통과' : 'every input passes here first'}</div>}</div>
              </div>
            )
          })}
        </div>
        <p className="small muted">{ko ? '검문소는 에이전트가 아니라 항상 켜져 있는 관문(코드)입니다. 보스가 부르거나 건너뛸 수 없고, 보스를 포함한 어떤 AI도 검사 전의 원본을 읽지 않습니다. 실행 기록마다 첫 단계로 표시됩니다.' : 'The Checkpoint is not an agent — it is an always-on gate in code that the Boss can neither call nor skip. No AI, the Boss included, reads unscreened input. It appears as step #1 of every run.'}</p>
        <div className="bench-grid">
          {roster.filter((a) => a.llm).map((a) => (
            <div key={a.id} className="bench-card" style={{ borderTopColor: a.color }}>
              <Bulldog costume={a.costume} furColor={a.color} size={56} />
              <div>
                <strong>{ko ? a.name_ko : a.name}</strong> {a.llm ? <Pill tone="blue">gpt-6-luna</Pill> : <Pill tone="gray">{ko ? '코드' : 'code'}</Pill>}
                <p className="small muted">{ko ? a.role_ko : a.role_en}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {tokens && (
        <>
          <div className="stats hero-stats">
            <Stat label={ko ? 'AI 실행 수' : 'AI runs'} value={num(tokens.total.runs)} />
            <Stat label={ko ? '입력 토큰' : 'Input tokens'} value={num(tokens.total.input_tokens)} hint={`${ko ? '캐시' : 'cached'} ${num(tokens.total.cached_tokens)} (${Math.round(cacheShare * 100)}%)`} />
            <Stat label={ko ? '출력 토큰' : 'Output tokens'} value={num(tokens.total.output_tokens)} />
            <Stat label={ko ? '총비용' : 'Total cost'} value={usd(tokens.total.cost_usd, 4)} hint={`$${tokens.price.input}/$${tokens.price.cached_input}/$${tokens.price.output} per 1M (in/cached/out)`} />
          </div>
          <div className="grid2">
            <Card title={ko ? '에이전트별 비용' : 'Cost by agent'}>
              <div className="bars" role="list">
                {tokens.by_agent.map((a) => (
                  <div key={a.agent} className="bar-row" role="listitem"
                    title={`${a.agent}: ${a.calls} calls · in ${num(a.input_tokens)} · cached ${num(a.cached_tokens)} · out ${num(a.output_tokens)} · ${usd(a.cost_usd, 5)}`}>
                    <span className="bar-label"><AgentChip id={a.agent} size={20} /></span>
                    <span className="bar-track"><span className="bar-fill" style={{ width: `${(a.cost_usd / maxCost) * 100}%` }} /></span>
                    <span className="bar-val">{usd(a.cost_usd, 4)}</span>
                  </div>
                ))}
              </div>
              <table className="tbl small-top">
                <thead><tr><th>{ko ? '에이전트' : 'Agent'}</th><th>{ko ? '호출' : 'Calls'}</th><th>in</th><th>cached</th><th>out</th><th>{ko ? '평균 시간' : 'avg time'}</th></tr></thead>
                <tbody>
                  {tokens.by_agent.map((a) => (
                    <tr key={a.agent}><td>{a.agent}</td><td>{a.calls}</td><td>{num(a.input_tokens)}</td><td>{num(a.cached_tokens)}</td><td>{num(a.output_tokens)}</td><td>{(a.avg_ms / 1000).toFixed(1)}s</td></tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title={ko ? '규모별 비용 (실측 평균 × 사용 가정)' : 'Cost at scale (measured averages × usage assumptions)'}>
              <table className="tbl">
                <thead><tr><th>{ko ? '작업' : 'Task'}</th><th>{ko ? '1회 평균' : 'avg / run'}</th><th>{ko ? '월 횟수' : 'runs / month'}</th><th>{ko ? '월 비용' : '$ / month'}</th></tr></thead>
                <tbody>
                  {perUser.rows.map((r) => {
                    const k = tokens.by_kind.find((x) => x.kind === r.kind)!
                    return <tr key={r.kind}><td>{USAGE[r.kind][ko ? 2 : 1]}</td><td>{usd(k.avg_cost, 5)}</td><td>{r.n.toFixed(2)}</td><td>{usd(r.c, 5)}</td></tr>
                  })}
                </tbody>
              </table>
              <div className="stats">
                <Stat label={ko ? '사용자 1명 / 월' : 'Per renter / month'} value={usd(perUser.cost, 4)} />
                <Stat label={ko ? '100명 / 월' : '100 renters / month'} value={usd(perUser.cost * 100, 2)} />
                <Stat label={ko ? '1만 명 / 월' : '10,000 renters / month'} value={usd(perUser.cost * 10000, 2)} />
                <Stat label={ko ? '1만 명 / 년' : '10,000 renters / year'} value={usd(perUser.cost * 10000 * 12, 2)} />
              </div>
              <p className="small muted">{ko ? `토큰 한도: 실행당 ${num(tokens.limits.run)}, 계정당 하루 ${num(tokens.limits.daily)}.` : `Guards: ${num(tokens.limits.run)} tokens per run, ${num(tokens.limits.daily)} per account per day.`}</p>
            </Card>
          </div>
        </>
      )}

      <div className="split">
        <div className="split-left">
          <Card title={ko ? '실행 기록' : 'Runs'}>
            {runs.map((r) => (
              <button key={r.id} className={`listrow ${sel === r.id ? 'on' : ''}`} onClick={() => setSel(r.id)}>
                <span className={`dot ${r.status}`} />
                <span className="grow">#{r.id} {r.title}</span>
                <span className="small muted">{usd(r.cost_usd, 4)}</span>
                <span className="small muted">{fmtDate(r.started_at, lang)}</span>
              </button>
            ))}
          </Card>
        </div>
        <div className="split-right">
          <RunPanel run={run} />
          {!run && <div className="empty">{ko ? '실행을 선택하면 에이전트 간 대화가 보입니다.' : 'Pick a run to see the agent-to-agent trace.'}</div>}
        </div>
      </div>
    </div>
  )
}
