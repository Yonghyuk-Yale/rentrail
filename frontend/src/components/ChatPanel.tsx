/** Chat with Chief Justice Dan. He answers, asks teammates, and acts: opens pages, checks off tasks,
 * moves the time machine, starts inspections / comparisons / cases. Used on Home, the Copilot page,
 * and as a floating dock on every other page. */

import { useEffect, useRef, useState } from 'react'
import { api, giveFocus } from '../api'
import { useApp } from '../i18n'
import Bulldog from './Bulldog'
import { AgentChip, useRun } from './RunPanel'
import { Markdownish } from './ui'

interface Action { type: string; label: string; page?: string; run_id?: number }
interface Answer {
  answer: string
  sources: string[]
  suggested_actions: string[]
  navigate_to: string | null
  buttons: { label: string; page: string }[]
  actions?: Action[]
}
interface Msg { role: 'user' | 'assistant'; content: string; run_id: number | null }

const SUGGEST: Record<string, [string, string][]> = {
  tenant: [
    ['What do I need to do this week?', '이번 주에 할 일이 뭐야?'],
    ['Show me my move-out deadlines', '퇴거 관련 기한 보여줘'],
    ['Is the carpet-cleaning charge fair?', '카펫 청소비 공제가 정당해?'],
    ['Compare my move-in and move-out videos', '입주·퇴거 영상 비교해줘'],
  ],
  sublessor: [
    ['What do I owe my subtenant under CT law?', '서브렛 세입자에게 CT 법상 뭘 해줘야 해?'],
    ['Draft the sublet documents', '서브렛 서류 작성해줘'],
    ['How much of the escrow goes back to Jordan?', '에스크로에서 Jordan에게 얼마 돌아가?'],
  ],
  subtenant: [
    ['When do I get my sublet deposit back?', '서브렛 보증금은 언제 돌려받아?'],
    ['What should I check at hand-off?', '인계 때 무엇을 확인해야 해?'],
    ['Open the escrow settlement', '에스크로 정산 열어줘'],
  ],
}

export default function ChatPanel({ variant, page }: { variant: 'home' | 'page' | 'dock'; page: string }) {
  const { lang, me, go, refreshMe, setBump } = useApp()
  const ko = lang === 'ko'
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [runId, setRunId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)

  const load = () => api.get<Msg[]>('/api/chat').then(setMsgs).catch(() => undefined)
  useEffect(() => {
    load()
  }, [])
  const run = useRun(runId, async (r) => {
    await load()
    const out = r.result as Answer | undefined
    if (!out) return
    out.actions?.filter((a) => a.type === 'run' && a.run_id && a.page).forEach((a) => giveFocus(a.page!, a.run_id!))
    const changed = out.actions?.some((a) => a.type === 'mode' || a.type === 'date' || a.type === 'task_done')
    if (changed) await refreshMe()
    if (out.navigate_to && out.navigate_to !== page) window.setTimeout(() => go(out.navigate_to!), 700)
    else if (changed) setBump((n) => n + 1)
  })
  useEffect(() => {
    const el = box.current
    if (!el) return
    el.scrollTop = el.scrollHeight // (scrollIntoView returns a Promise in new Chrome; keep effects void)
    const t = window.setTimeout(() => { el.scrollTop = el.scrollHeight }, 80)
    return () => window.clearTimeout(t)
  }, [msgs, run?.status])

  const busy = run?.status === 'running'
  const send = async (m: string) => {
    if (!m.trim() || busy) return
    setError(null)
    setText('')
    setMsgs((x) => [...x, { role: 'user', content: m, run_id: null }])
    try {
      setRunId((await api.post<{ run_id: number }>('/api/chat', { message: m, page })).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const shown = variant === 'dock' ? msgs.slice(-6) : msgs
  const lastCall = run?.calls?.[run.calls.length - 1]
  const mode = me?.user.mode ?? 'tenant'

  return (
    <div className={`chatpanel v-${variant}`}>
      <div className="chat-scroll" ref={box}>
        {shown.length === 0 && (
          <div className="chat-hello">
            <Bulldog costume="judge" furColor="#4f46e5" size={52} />
            <div>
              <strong>{ko ? '대법관 댄이에요. 무엇이든 물어보세요.' : 'I’m Chief Justice Dan. Ask me anything.'}</strong>
              <div className="small muted">{ko ? '답하고, 필요한 페이지를 열고, 점검·비교·서류 작성까지 직접 해 드려요.' : 'I answer, open the right page, and can run inspections, comparisons and documents for you.'}</div>
            </div>
          </div>
        )}
        {shown.map((m, i) => {
          if (m.role === 'user') return <div key={i} className="bubble me">{m.content}</div>
          let a: Answer | null = null
          try {
            a = JSON.parse(m.content) as Answer
          } catch {
            /* plain text */
          }
          return (
            <div key={i} className="bubble bot">
              <Bulldog costume="judge" furColor="#4f46e5" size={34} />
              <div className="bubble-body">
                {a ? <Markdownish text={a.answer} /> : m.content}
                {a?.actions?.length ? (
                  <div className="acts">
                    {a.actions.map((x, j) => (
                      <button key={j} className="act" onClick={() => x.page && go(x.page)}>
                        {x.type === 'run' ? '⚙️' : x.type === 'navigate' ? '➡️' : '✅'} {x.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                {a?.buttons?.length ? (
                  <div className="acts">
                    {a.buttons.map((b, j) => <button key={j} className="btn small" onClick={() => go(b.page)}>{b.label} →</button>)}
                  </div>
                ) : null}
                {a?.sources?.length ? <div className="srcs small muted">{a.sources.join(' · ')}</div> : null}
              </div>
            </div>
          )
        })}
        {busy && (
          <div className="bubble bot">
            <Bulldog costume="judge" furColor="#4f46e5" size={34} />
            <div className="pulse small">
              {lastCall && lastCall.agent !== 'chief_justice'
                ? <>{ko ? '팀원에게 묻는 중' : 'Asking'} <AgentChip id={lastCall.agent} size={18} /></>
                : (ko ? '생각 중…' : 'Thinking…')}
            </div>
          </div>
        )}
      </div>
      {error && <div className="alert small">{error}</div>}
      {msgs.length < 2 && (
        <div className="chat-suggest">
          {(SUGGEST[mode] ?? SUGGEST.tenant).map(([en, k]) => (
            <button key={en} className="sugg" onClick={() => send(ko ? k : en)}>{ko ? k : en}</button>
          ))}
        </div>
      )}
      <div className="chat-input">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send(text)}
          placeholder={mode === 'subtenant' ? (ko ? '예: 서브렛 보증금은 언제 돌려받아?' : 'e.g. When do I get my deposit back?') : (ko ? '예: 퇴거 통지는 언제까지 보내야 해?' : 'e.g. When is my move-out notice due?')} />
        <button className="btn primary" onClick={() => send(text)} disabled={busy}>{ko ? '보내기' : 'Send'}</button>
      </div>
    </div>
  )
}

export function ChatDock({ page }: { page: string }) {
  const { lang } = useApp()
  const [open, setOpen] = useState(false)
  return (
    <div className={`dock ${open ? 'open' : ''}`}>
      {open && (
        <div className="dock-box">
          <div className="dock-head">
            <strong>{lang === 'ko' ? '대법관 댄' : 'Chief Justice Dan'}</strong>
            <button className="modal-x static" onClick={() => setOpen(false)}>×</button>
          </div>
          <ChatPanel variant="dock" page={page} />
        </div>
      )}
      <button className="dock-btn" onClick={() => setOpen(!open)} title={lang === 'ko' ? '댄에게 묻기' : 'Ask Dan'}>
        <Bulldog costume="judge" furColor="#4f46e5" size={46} />
      </button>
    </div>
  )
}
