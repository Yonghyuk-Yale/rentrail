import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, fmtDate } from './api'
import Bulldog from './components/Bulldog'
import { ChatDock } from './components/ChatPanel'
import Tour, { TOUR } from './components/Tour'
import { AppCtx, translate, type Key } from './i18n'
import AgentRoom from './pages/AgentRoom'
import Bills from './pages/Bills'
import Community from './pages/Community'
import Copilot from './pages/Copilot'
import Court from './pages/Court'
import Home from './pages/Home'
import Inspections from './pages/Inspections'
import LeasePage from './pages/LeasePage'
import Login from './pages/Login'
import Safety from './pages/Safety'
import Sublet from './pages/Sublet'
import type { Agent, Lang, Me, User } from './types'

type Mode = User['mode']
interface NavItem { id: string; label: Key; icon: string; modes: Mode[] }

/** Which pages each role sees. A tenant who is not subletting sees Sublet locked. */
const NAV: { section: Key; items: NavItem[] }[] = [
  { section: 'section_record', items: [
    { id: 'home', label: 'home', icon: '🏠', modes: ['tenant', 'sublessor', 'subtenant'] },
    { id: 'lease', label: 'lease', icon: '📜', modes: ['tenant', 'sublessor', 'subtenant'] },
    { id: 'inspections', label: 'evidence', icon: '📸', modes: ['tenant', 'sublessor', 'subtenant'] },
    { id: 'court', label: 'court', icon: '⚖️', modes: ['tenant', 'sublessor', 'subtenant'] },
  ] },
  { section: 'section_money', items: [
    { id: 'sublet', label: 'sublet', icon: '🤝', modes: ['sublessor', 'subtenant'] },
    { id: 'bills', label: 'bills', icon: '🧾', modes: ['tenant', 'sublessor', 'subtenant'] },
  ] },
  { section: 'section_help', items: [
    { id: 'community', label: 'community', icon: '🗣️', modes: ['tenant', 'sublessor', 'subtenant'] },
  ] },
  { section: 'section_inside', items: [
    { id: 'agents', label: 'agents', icon: '🐶', modes: ['tenant', 'sublessor', 'subtenant'] },
    { id: 'safety', label: 'safety', icon: '🛡️', modes: ['tenant', 'sublessor', 'subtenant'] },
  ] },
]

/** Story dates (see backend/demo.py TIMELINE). Each role gets the moments that matter to it. */
const PRESETS: Record<string, { date: string; en: string; ko: string }[]> = {
  tenant: [
    { date: '2026-08-01', en: 'Move-in day', ko: '입주일' },
    { date: '2026-09-10', en: 'First bills', ko: '첫 고지서' },
    { date: '2027-05-20', en: 'Move-out notice due soon', ko: '퇴거 통지 직전' },
    { date: '2027-07-29', en: 'Move-out precheck', ko: '퇴거 전 진단' },
    { date: '2027-07-31', en: 'Move-out day', ko: '퇴거일' },
    { date: '2027-08-25', en: 'Deduction statement arrived', ko: '공제 내역서 도착' },
  ],
  sublessor: [
    { date: '2027-04-20', en: 'Sublet listed', ko: '서브렛 게시' },
    { date: '2027-05-12', en: 'Sublease signed', ko: '서브렛 계약 체결' },
    { date: '2027-06-01', en: 'Hand-off day', ko: '인계일' },
    { date: '2027-07-10', en: 'June bill arrived', ko: '6월 고지서 도착' },
    { date: '2027-07-29', en: 'Move-out precheck', ko: '퇴거 전 진단' },
    { date: '2027-07-30', en: 'Escrow settlement', ko: '에스크로 정산' },
  ],
  subtenant: [
    { date: '2027-04-30', en: 'Just matched', ko: '매칭 직후' },
    { date: '2027-05-15', en: 'Sublease signed', ko: '서브렛 계약 체결' },
    { date: '2027-06-01', en: 'Move-in (hand-off)', ko: '입주 (인계)' },
    { date: '2027-07-10', en: 'Utility share due', ko: '공과금 분담 기한' },
    { date: '2027-07-31', en: 'Settlement', ko: '정산' },
  ],
}

function pageFromHash() {
  return window.location.hash.replace(/^#\/?/, '') || 'home'
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [roster, setRoster] = useState<Agent[]>([])
  const [page, setPage] = useState(pageFromHash())
  const [bump, setBump] = useState(0)
  const [guestLang, setGuestLang] = useState<Lang>('en')
  const [clockOpen, setClockOpen] = useState(false)
  // Guided tour step (kept in sessionStorage so it survives page switches and the demo login).
  const [tour, setTourState] = useState<number | null>(null)
  const setTour = useCallback((n: number | null) => {
    if (n === null) sessionStorage.removeItem('rentrail_tour')
    else sessionStorage.setItem('rentrail_tour', String(n))
    setTourState(n)
  }, [])
  const lang: Lang = me?.user.lang ?? guestLang
  const mode: Mode = me?.user.mode ?? 'tenant'

  const refreshMe = useCallback(async () => {
    try {
      setMe(await api.get<Me>('/api/me'))
    } catch {
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshMe()
    // The roster drives every bulldog on screen; retry if the server was still starting.
    const loadRoster = (tries: number) =>
      api.get<Agent[]>('/api/agents').then(setRoster).catch(() => tries > 0 && window.setTimeout(() => loadRoster(tries - 1), 1500))
    loadRoster(10)
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [refreshMe])

  const go = useCallback((p: string) => {
    window.location.hash = `/${p}`
    window.scrollTo({ top: 0 })
  }, [])

  const ctx = useMemo(
    () => ({ lang, me, roster, t: (k: Key) => translate(lang, k), refreshMe, go, bump, setBump }),
    [lang, me, roster, refreshMe, go, bump],
  )

  const patchMe = async (body: Record<string, unknown>) => {
    await api.patch('/api/me', body)
    await refreshMe()
    setBump((n) => n + 1)
  }
  useEffect(() => {
    const saved = sessionStorage.getItem('rentrail_tour')
    if (me && saved !== null) setTourState(Math.min(Number(saved) || 0, TOUR.length - 1))
  }, [me?.user.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const applyTour = async (st: (typeof TOUR)[number]) => {
    if (me && (me.today !== st.date || me.user.mode !== st.mode)) await patchMe({ demo_today: st.date, mode: st.mode })
    go(st.page)
  }
  const isAlex = me?.user.email === 'alex@demo.rentrail'
  const setLang = async (l: Lang) => (me ? patchMe({ lang: l }) : setGuestLang(l))
  const logout = async () => {
    await api.post('/api/auth/logout')
    setMe(null)
    go('home')
  }

  const t = ctx.t
  const ko = lang === 'ko'
  const allowed = (it: NavItem) => it.modes.includes(mode)
  const current = NAV.flatMap((s) => s.items).find((i) => i.id === page)
  const blocked = current && !allowed(current)

  let body
  if (loading) body = <div className="center muted">…</div>
  else if (!me) body = <Login onLang={setLang} />
  else
    body = (
      <div className="shell">
        <aside className="side">
          <div className="brand" onClick={() => go('home')}>
            <Bulldog costume="plain" furColor="#e9d5b7" size={40} />
            <div>
              <div className="brand-name">Rentrail</div>
              <div className="brand-tag">{t('tagline')}</div>
            </div>
          </div>
          {NAV.map((sec) => {
            const items = sec.items.filter((it) => allowed(it) || (it.id === 'sublet' && mode === 'tenant'))
            if (!items.length) return null
            return (
              <nav key={sec.section}>
                <div className="nav-sec">{t(sec.section)}</div>
                {items.map((it) => {
                  const locked = !allowed(it)
                  return (
                    <button key={it.id} className={`nav-item ${page === it.id ? 'on' : ''} ${locked ? 'locked' : ''}`}
                      title={locked ? (ko ? '"서브렛 내주기" 모드에서 열립니다' : 'Opens in "Subletting my place" mode') : ''}
                      onClick={() => (locked ? patchMe({ mode: 'sublessor' }).then(() => go(it.id)) : go(it.id))}>
                      <span className="nav-ico">{locked ? '🔒' : it.icon}</span>
                      {t(it.label)}
                    </button>
                  )
                })}
              </nav>
            )
          })}
        </aside>
        <div className="main">
          <div className="topbar">
            <div className="role">
              {mode === 'subtenant' ? (
                <span className="pill amber">🎒 {ko ? '서브렛 세입자' : 'Subtenant'}</span>
              ) : (
                <div className="seg">
                  <button className={mode === 'tenant' ? 'on' : ''} onClick={() => patchMe({ mode: 'tenant' })}>🏠 {ko ? '세입자' : 'Renting'}</button>
                  <button className={mode === 'sublessor' ? 'on' : ''} onClick={() => patchMe({ mode: 'sublessor' })}>🤝 {ko ? '서브렛 내주기' : 'Subletting my place'}</button>
                </div>
              )}
            </div>
            <div className="top-right">
              {isAlex && tour === null && (
                <button className="btn small tour-start" onClick={() => setTour(0)}>▶ {ko ? '2분 투어' : '2-min tour'}</button>
              )}
              <div className="clock">
                <button className="btn ghost small" onClick={() => setClockOpen(!clockOpen)} title={t('demo_date')}>
                  🕰️ {fmtDate(me.today, lang)} ▾
                </button>
                {clockOpen && (
                  <div className="clock-pop" onMouseLeave={() => setClockOpen(false)}>
                    <div className="small muted">{t('demo_date')}</div>
                    {(PRESETS[mode] ?? PRESETS.tenant).map((p) => (
                      <button key={p.date} className={`preset ${me.today === p.date ? 'on' : ''}`}
                        onClick={() => { patchMe({ demo_today: p.date }); setClockOpen(false) }}>
                        {ko ? p.ko : p.en} · {fmtDate(p.date, lang)}
                      </button>
                    ))}
                    <input type="date" value={me.today} onChange={(e) => e.target.value && patchMe({ demo_today: e.target.value })} />
                  </div>
                )}
              </div>
              <div className="lang">
                <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')}>EN</button>
                <button className={lang === 'ko' ? 'on' : ''} onClick={() => setLang('ko')}>한국어</button>
              </div>
              <span className="who">{me.user.name}</span>
              <button className="btn ghost small" onClick={logout}>{t('logout')}</button>
            </div>
          </div>
          <div className="content" key={`${page}-${bump}`}>
            {blocked ? (
              <div className="empty">
                {ko ? '이 역할에서는 볼 수 없는 페이지입니다.' : 'This page is not part of your current role.'}{' '}
                <button className="btn small" onClick={() => go('home')}>{t('home')}</button>
              </div>
            ) : (
              <>
                {page === 'home' && <Home />}
                {page === 'lease' && <LeasePage />}
                {page === 'inspections' && <Inspections />}
                {page === 'court' && <Court />}
                {page === 'sublet' && <Sublet />}
                {page === 'bills' && <Bills />}
                {page === 'copilot' && <Copilot />}
                {page === 'community' && <Community />}
                {page === 'agents' && <AgentRoom />}
                {page === 'safety' && <Safety />}
              </>
            )}
          </div>
        </div>
        {page !== 'copilot' && <ChatDock page={page} />}
        {tour !== null && <Tour step={tour} setStep={setTour} apply={applyTour} />}
      </div>
    )

  return (
    <AppCtx.Provider value={ctx}>
      <div className="yale-bar">YALE SOM - Yonghyuk Choi</div>
      {body}
      <div className="yale-bar bottom">YALE SOM - Yonghyuk Choi</div>
    </AppCtx.Provider>
  )
}
