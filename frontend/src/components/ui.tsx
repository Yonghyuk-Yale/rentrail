import { useState, type ReactNode } from 'react'
import { api, fileUrl } from '../api'
import { useApp } from '../i18n'
import type { Evidence } from '../types'
import Bulldog from './Bulldog'

export function Card({ title, children, right, className = '' }: { title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <header className="card-head">
          <h3>{title}</h3>
          <div>{right}</div>
        </header>
      )}
      {children}
    </section>
  )
}

export function PageHead({ title, sub, agent, color, actions }: { title: string; sub?: string; agent?: Parameters<typeof Bulldog>[0]['costume']; color?: string; actions?: ReactNode }) {
  return (
    <div className="pagehead">
      {agent && <Bulldog costume={agent} furColor={color} size={46} />}
      <div className="grow">
        <h2>{title}</h2>
        {sub && <p className="muted small">{sub}</p>}
      </div>
      {actions && <div className="pagehead-actions">{actions}</div>}
    </div>
  )
}

/** A summary tile: one big value, a short label, an optional hint. Click to go deeper. */
export function Kpi({ label, value, hint, tone = 'plain', onClick }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: 'plain' | 'good' | 'warn' | 'bad'; onClick?: () => void
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag className={`kpi ${tone} ${onClick ? 'clickable' : ''}`} onClick={onClick}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </Tag>
  )
}

/** Summary line first; the detail opens on click. */
export function Disclosure({ summary, children, defaultOpen = false, right, count }: {
  summary: ReactNode; children: ReactNode; defaultOpen?: boolean; right?: ReactNode; count?: number
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`disc ${open ? 'open' : ''}`}>
      {/* A div with the button role: the header may hold its own buttons (no button inside a button). */}
      <div className="disc-head" role="button" tabIndex={0} aria-expanded={open} onClick={() => setOpen(!open)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget && (e.preventDefault(), setOpen(!open))}>
        <span className="disc-caret">{open ? '▾' : '▸'}</span>
        <span className="disc-title">{summary}</span>
        {count !== undefined && <span className="disc-count">{count}</span>}
        {right && <span className="disc-right" onClick={(e) => e.stopPropagation()}>{right}</span>}
      </div>
      {open && <div className="disc-body">{children}</div>}
    </div>
  )
}

/** A one-line row that expands into details below it. */
export function RowItem({ left, main, sub, right, children, tone }: {
  left?: ReactNode; main: ReactNode; sub?: ReactNode; right?: ReactNode; children?: ReactNode; tone?: 'warn' | 'bad' | 'good'
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`rowitem ${open ? 'open' : ''} ${tone ?? ''}`}>
      <div className={`rowitem-head ${children ? '' : 'static'}`} role={children ? 'button' : undefined} tabIndex={children ? 0 : undefined}
        aria-expanded={children ? open : undefined} onClick={() => children && setOpen(!open)}
        onKeyDown={(e) => children && (e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget && (e.preventDefault(), setOpen(!open))}>
        {left && <span className="rowitem-left">{left}</span>}
        <span className="rowitem-main">
          <span className="rowitem-title">{main}</span>
          {sub && <span className="rowitem-sub">{sub}</span>}
        </span>
        {right && <span className="rowitem-right">{right}</span>}
        {children && <span className="disc-caret">{open ? '▾' : '▸'}</span>}
      </div>
      {open && children && <div className="rowitem-body">{children}</div>}
    </div>
  )
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Pill({ tone = 'blue', children }: { tone?: 'blue' | 'green' | 'red' | 'amber' | 'gray' | 'purple'; children: ReactNode }) {
  return <span className={`pill ${tone}`}>{children}</span>
}

export function Err({ error }: { error: string | null }) {
  return error ? <div className="alert">{error}</div> : null
}

export function EvidenceThumb({ ev, onOpen, highlight }: { ev: Evidence; onOpen?: (ev: Evidence) => void; highlight?: boolean }) {
  return (
    <button className={`thumb ${highlight ? 'hl' : ''}`} onClick={() => onOpen?.(ev)} title={ev.label}>
      <img src={fileUrl(ev.file_id, ev.sha256)} alt={ev.label} loading="lazy" />
      <span className="thumb-id">E{ev.id}</span>
      {ev.t_seconds !== null && <span className="thumb-t">▶ {ev.t_seconds}s</span>}
    </button>
  )
}

export function EvidenceModal({ ev, onClose }: { ev: Evidence | null; onClose: () => void }) {
  const { t, lang } = useApp()
  const [check, setCheck] = useState<{ intact: boolean; sha256: string } | null>(null)
  if (!ev) return null
  const meta = ev.meta as Record<string, unknown>
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose}>
          ×
        </button>
        <img src={fileUrl(ev.file_id, ev.sha256)} alt={ev.label} className="modal-img" />
        <div className="modal-meta">
          <div>
            <strong>Exhibit E{ev.id}</strong> · {ev.room} · {ev.label}
          </div>
          <div className="muted">
            {lang === 'ko' ? '업로드' : 'Uploaded'} {ev.uploaded_at}
            {meta?.gps_removed ? ` · ${lang === 'ko' ? 'GPS 제거됨' : 'GPS removed'}` : ''}
            {meta?.exif_removed ? ` · EXIF ${lang === 'ko' ? '제거됨' : 'removed'}` : ''}
            {Number(meta?.faces_blurred) > 0 ? ` · ${String(meta.faces_blurred)} ${lang === 'ko' ? '얼굴 흐림' : 'face(s) blurred'}` : ''}
          </div>
          <div className="mono small">
            {t('fingerprint')}: {ev.sha256}
          </div>
          <button
            className="btn ghost small"
            onClick={async () => setCheck(await api.get(`/api/files/${ev.file_id}/verify`))}
          >
            {t('verify')}
          </button>
          {check && <span className={check.intact ? 'ok' : 'bad'}>{check.intact ? ` ✓ ${t('intact')}` : ' ✗ MISMATCH'}</span>}
        </div>
      </div>
    </div>
  )
}

export function Markdownish({ text }: { text: string }) {
  // Tiny renderer: paragraphs, bullet lines, **bold**. Enough for agent answers and letters.
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="md">
      {blocks.map((b, i) => {
        const lines = b.split('\n').filter((l) => l.trim())
        if (lines.length >= 2 && lines.every((l) => l.trim().startsWith('|'))) {
          const cells = (l: string) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
          const rows = lines.filter((l) => !/^\s*\|?\s*:?-{2,}/.test(l))
          return (
            <table key={i}>
              <thead><tr>{cells(rows[0]).map((c, j) => <th key={j} dangerouslySetInnerHTML={{ __html: inline(c) }} />)}</tr></thead>
              <tbody>
                {rows.slice(1).map((r, j) => <tr key={j}>{cells(r).map((c, k) => <td key={k} dangerouslySetInnerHTML={{ __html: inline(c) }} />)}</tr>)}
              </tbody>
            </table>
          )
        }
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s/.test(l)))
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j} dangerouslySetInnerHTML={{ __html: inline(l.replace(/^\s*([-*]|\d+\.)\s/, '')) }} />
              ))}
            </ul>
          )
        return <p key={i} dangerouslySetInnerHTML={{ __html: inline(b).replace(/\n/g, '<br/>') }} />
      })}
    </div>
  )
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function inline(s: string) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^#{1,4}\s*(.+)$/gm, '<strong>$1</strong>')
}
