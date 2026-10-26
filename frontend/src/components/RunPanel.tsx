/** Live trace of one run: which bulldog called which, what was sent, what came back, tokens and cost.
 * Polls /api/runs/:id until the run is done. Used on every page that starts AI work. */

import { useEffect, useRef, useState } from 'react'
import { api, num, usd } from '../api'
import { useApp } from '../i18n'
import type { AgentCall, Run } from '../types'
import Bulldog from './Bulldog'

export function useRun(runId: number | null, onDone?: (run: Run) => void) {
  const [run, setRun] = useState<Run | null>(null)
  const done = useRef(onDone)
  done.current = onDone
  useEffect(() => {
    if (!runId) {
      setRun(null)
      return
    }
    let stop = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const r = await api.get<Run>(`/api/runs/${runId}`)
        if (stop) return
        setRun(r)
        if (r.status === 'running') timer = window.setTimeout(tick, 1500)
        else done.current?.(r)
      } catch {
        if (!stop) timer = window.setTimeout(tick, 3000)
      }
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [runId])
  return run
}

export function AgentChip({ id, size = 28 }: { id: string; size?: number }) {
  const { roster, lang } = useApp()
  const a = roster.find((r) => r.id === id)
  if (id === 'user')
    return (
      <span className="chip">
        <span className="chip-you">👤</span> {lang === 'ko' ? '사용자' : 'You'}
      </span>
    )
  return (
    <span className="chip" style={{ borderColor: a?.color }}>
      <Bulldog costume={a?.costume ?? 'plain'} furColor={a?.color ?? '#e9d5b7'} size={size} />
      {a ? (lang === 'ko' ? a.name_ko : a.name) : id}
    </span>
  )
}

function CallRow({ c }: { c: AgentCall }) {
  const { t } = useApp()
  const [open, setOpen] = useState(false)
  return (
    <div className={`call ${c.status}`}>
      <button className="call-head" onClick={() => setOpen(!open)}>
        <span className="seq">#{c.seq}</span>
        <AgentChip id={c.caller} size={22} />
        <span className="arrow">→</span>
        <AgentChip id={c.agent} size={22} />
        <span className="purpose">{c.purpose}</span>
        <span className="tok">
          {c.status === 'running' ? (
            <span className="pulse">{t('running')}</span>
          ) : (
            <>
              in {num(c.input_tokens)} · cached {num(c.cached_tokens)} · out {num(c.output_tokens)} · {usd(c.cost_usd, 5)} ·{' '}
              {c.ms ? `${(c.ms / 1000).toFixed(1)}s` : ''}
            </>
          )}
        </span>
        <span className="caret">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="call-body">
          <div>
            <h5>{t('input')}</h5>
            <pre>{c.input_preview}</pre>
          </div>
          <div>
            <h5>{t('output')}</h5>
            <pre>{typeof c.output === 'string' ? c.output : JSON.stringify(c.output, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  )
}

export default function RunPanel({ run, compact = false }: { run: Run | null; compact?: boolean }) {
  const { t, lang } = useApp()
  if (!run) return null
  const calls = run.calls ?? []
  return (
    <div className={`runpanel ${run.status}`}>
      <div className="runpanel-head">
        <strong>{t('live_trace')}</strong>
        <span className={`badge ${run.status}`}>{run.status === 'running' ? t('running') : run.status}</span>
        <span className="muted">
          run #{run.id} · in {num(run.input_tokens)} · cached {num(run.cached_tokens)} · out {num(run.output_tokens)} ·{' '}
          {t('cost')} {usd(run.cost_usd, 5)}
        </span>
      </div>
      {run.error && (
        <div className="alert">
          {lang === 'ko' ? '실행 실패: ' : 'Run failed: '}
          {run.error}
        </div>
      )}
      {!compact && calls.map((c) => <CallRow key={c.id} c={c} />)}
      {compact && calls.length > 0 && (
        <div className="call-mini">
          {calls.map((c) => (
            <span key={c.id} title={`${c.agent}: ${c.purpose}`}>
              <AgentChip id={c.agent} size={20} />
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
