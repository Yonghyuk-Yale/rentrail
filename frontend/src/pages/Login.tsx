import { useState } from 'react'
import { api } from '../api'
import Bulldog from '../components/Bulldog'
import Gate from '../components/Gate'
import { Err } from '../components/ui'
import { useApp } from '../i18n'
import type { Lang } from '../types'

export default function Login({ onLang }: { onLang: (l: Lang) => void }) {
  const { t, lang, refreshMe, roster } = useApp()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') await api.post('/api/auth/login', { email, password })
      else await api.post('/api/auth/register', { email, name, password, lang })
      await refreshMe()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const demo = async (who: string) => {
    setBusy(true)
    try {
      await api.post('/api/auth/demo', { who })
      await refreshMe()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="login-hero">
        <div className="lang">
          <button className={lang === 'en' ? 'on' : ''} onClick={() => onLang('en')}>EN</button>
          <button className={lang === 'ko' ? 'on' : ''} onClick={() => onLang('ko')}>한국어</button>
        </div>
        <h1>
          Rentrail <span className="hero-tag">{t('tagline')}</span>
        </h1>
        <p className="lead">{t('pitch')}</p>
        <div className="bench">
          {roster.filter((a) => a.llm).map((a) => (
            <div key={a.id} className="bench-dog" title={lang === 'ko' ? a.role_ko : a.role_en}>
              <Bulldog costume={a.costume} furColor={a.color} size={86} />
              <div className="bench-name">{lang === 'ko' ? a.name_ko : a.name}</div>
            </div>
          ))}
        </div>
        <div className="gate-line">
          <Gate size={44} />
          <span className="small">
            {lang === 'ko'
              ? '모든 사진·문서·질문은 AI보다 먼저 검문소(코드)를 지나갑니다: 숨은 지시문 차단, GPS·얼굴·개인정보 제거.'
              : 'Every photo, document and question passes the Checkpoint (plain code) before any AI: hidden instructions blocked, GPS, faces and personal data removed.'}
          </span>
        </div>
        <p className="muted small">{t('not_legal')}</p>
      </div>
      <div className="login-box">
        <h3>{t('try_demo')}</h3>
        <p className="muted small">
          {lang === 'ko'
            ? '가상의 Yale 학생 Alex의 1년 임대 기록이 미리 채워져 있습니다. 비밀번호 없이 바로 들어갈 수 있습니다.'
            : 'A fictional Yale student’s full year of renting is pre-loaded. One click, no password.'}
        </p>
        <button className="btn primary block tour-cta" disabled={busy} onClick={() => { sessionStorage.setItem('rentrail_tour', '0'); demo('alex') }}>
          ▶ {lang === 'ko' ? '2분 가이드 투어 — Alex의 1년' : '2-minute guided tour — Alex’s year'}
        </button>
        <button className="btn block" disabled={busy} onClick={() => demo('alex')}>
          🐶 {t('demo_alex')}
        </button>
        <button className="btn block" disabled={busy} onClick={() => demo('jordan')}>
          🎒 {t('demo_jordan')}
        </button>
        <div className="or">
          <span>or</span>
        </div>
        <form onSubmit={submit}>
          <div className="tabs small">
            <button type="button" className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>
              {t('login')}
            </button>
            <button type="button" className={mode === 'register' ? 'on' : ''} onClick={() => setMode('register')}>
              {t('register')}
            </button>
          </div>
          {mode === 'register' && (
            <label>
              {t('name')}
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
          )}
          <label>
            {t('email')}
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            {t('password')}
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required />
          </label>
          <Err error={error} />
          <button className="btn primary block" disabled={busy}>
            {mode === 'login' ? t('login') : t('register')}
          </button>
          <p className="muted small">
            {lang === 'ko'
              ? '비밀번호는 원문이 아닌 해시로만 저장되고, 업로드한 파일은 암호화되어 저장됩니다.'
              : 'Passwords are stored only as salted hashes; every upload is encrypted on disk.'}
          </p>
        </form>
      </div>
    </div>
  )
}
