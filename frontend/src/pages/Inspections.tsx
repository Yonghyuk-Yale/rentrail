/** Inspections: pick a record at the top, see its findings as one-line rows (click for details),
 * photos and videos are folded away, and before-vs-after lives in its own panel. */

import { useEffect, useMemo, useState } from 'react'
import { api, fileUrl, fmtDate, takeFocus } from '../api'
import RunPanel, { useRun } from '../components/RunPanel'
import { Card, Disclosure, Empty, Err, EvidenceModal, EvidenceThumb, Kpi, PageHead, Pill, RowItem } from '../components/ui'
import { pick, useApp } from '../i18n'
import type { Comparison, Evidence, Finding, Inspection } from '../types'

const KIND_LABEL: Record<string, [string, string]> = {
  move_in: ['Move-in', '입주'],
  move_out: ['Move-out', '퇴거'],
  sublet_handoff: ['Sublet hand-off', '서브렛 인계'],
  sublet_return: ['Sublet return', '서브렛 반환'],
}
const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'gray'> = {
  pre_existing: 'green', new_damage: 'red', wear_and_tear: 'amber', unclear: 'gray',
}
const STATUS_LABEL: Record<string, [string, string]> = {
  pre_existing: ['Already there before', '이전부터 있던 하자'],
  new_damage: ['New damage', '새 손상'],
  wear_and_tear: ['Normal wear and tear', '정상 마모'],
  unclear: ['Unclear', '불명확'],
}
const ROOMS = ['Living room', 'Bedroom', 'Kitchen', 'Bathroom', 'Hallway', 'Other']

export function kindLabel(kind: string, lang: 'en' | 'ko') {
  return (KIND_LABEL[kind] ?? [kind, kind])[lang === 'ko' ? 1 : 0]
}

type Dismissed = Finding & { dismiss_reason?: string; dismissed_by?: string }

function FindingItem({ f, evidence, onOpen, actionLabel, onAction }: {
  f: Dismissed; evidence: Evidence[]; onOpen: (e: Evidence) => void; actionLabel?: string; onAction?: () => void
}) {
  const { lang } = useApp()
  const ev = evidence.find((e) => e.id === f.evidence_id)
  return (
    <RowItem
      left={ev ? <img className="mini-thumb" src={fileUrl(ev.file_id, ev.sha256)} alt="" /> : undefined}
      main={<>{f.room} · {f.item} — {f.damage_type}</>}
      sub={f.dismiss_reason ? `🙅 ${f.dismiss_reason}` : f.location}
      right={<Pill tone={f.severity === 3 ? 'red' : f.severity === 2 ? 'amber' : 'gray'}>{lang === 'ko' ? `심각도 ${f.severity}` : `sev ${f.severity}`}</Pill>}
    >
      <div className="finding-detail">
        {ev && <EvidenceThumb ev={ev} onOpen={onOpen} />}
        <div className="grow">
          <p className="small">{pick(f as unknown as Record<string, unknown>, 'description', lang)}</p>
          <p className="small muted">📍 {f.location} · {Math.round(f.confidence * 100)}%</p>
          {onAction && <button className="btn ghost small" onClick={onAction}>{actionLabel}</button>}
        </div>
      </div>
    </RowItem>
  )
}

export default function Inspections() {
  const { lang, me } = useApp()
  const ko = lang === 'ko'
  const [list, setList] = useState<Inspection[]>([])
  const [sel, setSel] = useState<number | null>(null)
  const [runId, setRunId] = useState<number | null>(null)
  const [cmpRun, setCmpRun] = useState<number | null>(null)
  const [showCompare, setShowCompare] = useState(false)
  const [open, setOpen] = useState<Evidence | null>(null)
  const [room, setRoom] = useState('Living room')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newKind, setNewKind] = useState('move_in')
  const [earlier, setEarlier] = useState<number | ''>('')
  const [later, setLater] = useState<number | ''>('')

  const load = async () => {
    const l = await api.get<Inspection[]>('/api/inspections')
    setList(l)
    setSel((cur) => (cur && l.some((i) => i.id === cur) ? cur : l[0]?.id ?? null))
  }
  useEffect(() => {
    load()
    const f = takeFocus('inspections')
    if (f)
      api.get<{ kind: string; ref: string | null }>(`/api/runs/${f}`).then((r) => {
        if (r.kind === 'compare') { setCmpRun(f); setShowCompare(true) }
        else {
          setRunId(f)
          const m = /inspection:(\d+)/.exec(r.ref ?? '')
          if (m) setSel(Number(m[1]))
        }
      })
  }, [])
  const run = useRun(runId, () => load())
  const cmp = useRun(cmpRun)
  const insp = list.find((i) => i.id === sel) ?? null
  const allEvidence = useMemo(() => list.flatMap((i) => i.evidence), [list])

  const create = async () => {
    const r = await api.post<Inspection>('/api/inspections', { kind: newKind, inspected_on: me?.today })
    await load()
    setSel(r.id)
  }
  const upload = async (files: FileList | null) => {
    if (!files || !insp) return
    setBusy(true)
    setError(null)
    const fd = new FormData()
    Array.from(files).forEach((f) => fd.append('files', f))
    fd.append('room', room)
    try {
      await api.upload(`/api/inspections/${insp.id}/media`, fd)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const inspect = async () => {
    if (!insp) return
    setError(null)
    try {
      setRunId((await api.post<{ run_id: number }>(`/api/inspections/${insp.id}/run`)).run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const compare = async () => {
    if (!earlier || !later) return
    setCmpRun((await api.post<{ run_id: number }>('/api/compare', { earlier_id: earlier, later_id: later })).run_id)
  }
  const review = async (action: 'dismiss' | 'restore', index: number) => {
    if (!insp) return
    let reason: string | null = null
    if (action === 'dismiss') {
      reason = window.prompt(ko ? '하자가 아닌 이유 (예: 조명 반사, 원래 무늬)' : 'Why is this not damage? (e.g. light reflection, wood grain)', ko ? '조명·무늬로 인한 오인' : 'Lighting / texture, not damage')
      if (reason === null) return
    }
    await api.post(`/api/inspections/${insp.id}/review`, { action, index, reason })
    load()
  }

  const byRoom = useMemo(() => {
    const m = new Map<string, Evidence[]>()
    insp?.evidence.forEach((e) => m.set(e.room, [...(m.get(e.room) ?? []), e]))
    return [...m.entries()]
  }, [insp])
  const res = insp?.result
  const dismissed = ((res as { dismissed?: Dismissed[] } | null)?.dismissed ?? [])
  const comparison = cmp?.result as Comparison | undefined
  const photos = insp?.evidence.filter((e) => e.parent_file_id === null).length ?? 0

  return (
    <div>
      <PageHead title={ko ? '점검' : 'Inspections'}
        sub={ko ? '사진·영상으로 집 상태를 기록하고 전후를 비교합니다.' : 'Record the condition in photos and video, then compare before vs. after.'}
        agent="detective" color="#f97316"
        actions={<button className={`btn small ${showCompare ? 'primary' : ''}`} onClick={() => {
          // Prefill: the record before the selected one vs. the selected one.
          const at = list.findIndex((i) => i.id === sel)
          if (!showCompare && at > 0 && !earlier && !later) { setEarlier(list[at - 1].id); setLater(list[at].id) }
          setShowCompare(!showCompare)
        }}>🔁 {ko ? '전후 비교' : 'Before vs. after'}</button>} />

      <div className="record-tabs">
        {list.map((i) => (
          <button key={i.id} className={`record-tab ${sel === i.id ? 'on' : ''}`} onClick={() => setSel(i.id)}>
            <span className="record-kind">{i.title.startsWith('Safety test') ? `🛡️ ${ko ? '안전 테스트' : 'Safety test'}` : kindLabel(i.kind, lang)}</span>
            <span className="record-date">{fmtDate(i.inspected_on, lang)}</span>
            <span className="record-count">{i.result ? `${i.result.findings.length} ${ko ? '건' : 'found'}` : (ko ? '점검 전' : 'not run')}</span>
          </button>
        ))}
        <span className="record-new">
          <select value={newKind} onChange={(e) => setNewKind(e.target.value)}>
            {Object.keys(KIND_LABEL).map((k) => <option key={k} value={k}>{kindLabel(k, lang)}</option>)}
          </select>
          <button className="btn small" onClick={create}>+ {ko ? '새 점검' : 'New'}</button>
        </span>
      </div>

      {showCompare && (
        <Card title={ko ? '전후 비교' : 'Before vs. after'}>
          <div className="row gap">
            <select value={earlier} onChange={(e) => setEarlier(Number(e.target.value) || '')}>
              <option value="">{ko ? '이전 기록' : 'Earlier record'}</option>
              {list.map((i) => <option key={i.id} value={i.id}>{kindLabel(i.kind, lang)} · {fmtDate(i.inspected_on, lang)}</option>)}
            </select>
            <span>→</span>
            <select value={later} onChange={(e) => setLater(Number(e.target.value) || '')}>
              <option value="">{ko ? '나중 기록' : 'Later record'}</option>
              {list.map((i) => <option key={i.id} value={i.id}>{kindLabel(i.kind, lang)} · {fmtDate(i.inspected_on, lang)}</option>)}
            </select>
            <button className="btn primary small" onClick={compare} disabled={!earlier || !later || cmp?.status === 'running'}>{ko ? '비교' : 'Compare'}</button>
          </div>
          {cmp?.status === 'running' && <RunPanel run={cmp} compact />}
          {comparison && (
            <>
              <p className="small">{pick(comparison as unknown as Record<string, unknown>, 'summary', lang)}</p>
              {comparison.items.map((it, i) => {
                const lev = allEvidence.find((e) => e.id === it.later.evidence_id)
                const eid = it.earlier?.evidence_id ?? it.earlier_evidence_id
                const eev = eid ? allEvidence.find((e) => e.id === eid) : null
                return (
                  <RowItem key={i} main={<>{it.later.room} · {it.later.item} — {it.later.damage_type}</>}
                    right={<Pill tone={STATUS_TONE[it.status]}>{STATUS_LABEL[it.status][ko ? 1 : 0]}</Pill>}>
                    <div className="pair-imgs">
                      <div><div className="small muted">{ko ? '이전 (같은 위치)' : 'Before (same spot)'}</div>{eev ? <EvidenceThumb ev={eev} onOpen={setOpen} /> : <div className="thumb empty-thumb">—</div>}</div>
                      <div><div className="small muted">{ko ? '이후' : 'After'}</div>{lev && <EvidenceThumb ev={lev} onOpen={setOpen} />}</div>
                    </div>
                    <p className="small">{pick(it as unknown as Record<string, unknown>, 'reason', lang)}</p>
                  </RowItem>
                )
              })}
            </>
          )}
        </Card>
      )}

      <Err error={error} />
      {!insp ? (
        <Empty>{ko ? '점검 기록을 만들어 사진이나 영상을 올리세요.' : 'Create a record and add photos or video.'}</Empty>
      ) : (
        <Card title={<>{kindLabel(insp.kind, lang)} · {fmtDate(insp.inspected_on, lang)}</>}
          right={<button className="btn primary small" onClick={inspect} disabled={run?.status === 'running' || !insp.evidence.length}>🔎 {res ? (ko ? '다시 점검' : 'Run again') : (ko ? '형사 댄 점검' : 'Inspect')}</button>}>
          {run?.status === 'running' && <RunPanel run={run} compact />}
          <div className="kpis">
            <Kpi label={ko ? '사진' : 'Photos'} value={photos} />
            <Kpi label={ko ? '영상' : 'Videos'} value={insp.videos.length} hint={insp.videos.length ? `${insp.evidence.length - photos} ${ko ? '장면' : 'frames'}` : ''} />
            <Kpi label={ko ? '하자' : 'Defects'} value={res ? res.findings.length : '—'} tone={res && res.findings.length ? 'warn' : res ? 'good' : 'plain'} hint={res ? '' : (ko ? '점검 전' : 'not inspected')} />
            <Kpi label={ko ? '사람이 제외' : 'Dismissed'} value={dismissed.length} hint={ko ? '오탐을 직접 제외' : 'false alarms you removed'} />
          </div>
          {res?.injection_blocked && (
            <div className="alert-row warn">🛂 {ko ? '사진 속 AI 지시문("' : 'Text addressed to the AI ("'}{res.seen_text.find((t) => t.blocked)?.text}{ko ? '")을 검문소가 무시했고, 하자는 그대로 보고했습니다.' : '") was ignored; the damage was still reported.'}</div>
          )}
          {res && (
            <>
              {res.findings.length === 0 && <p className="muted small">{ko ? '하자 없음.' : 'No damage found.'}</p>}
              {res.findings.map((f, i) => (
                <FindingItem key={i} f={f} evidence={insp.evidence} onOpen={setOpen} actionLabel={ko ? '하자 아님으로 제외' : 'Not damage — dismiss'} onAction={() => review('dismiss', i)} />
              ))}
              {dismissed.length > 0 && (
                <Disclosure summary={ko ? '사람이 확인해 제외한 항목' : 'Dismissed after human review'} count={dismissed.length}>
                  {dismissed.map((f, i) => (
                    <FindingItem key={i} f={f} evidence={insp.evidence} onOpen={setOpen} actionLabel={ko ? '되돌리기' : 'Restore'} onAction={() => review('restore', i)} />
                  ))}
                </Disclosure>
              )}
            </>
          )}
          <Disclosure summary={ko ? '사진·영상' : 'Photos & videos'} count={insp.evidence.length}>
            <div className="row gap upload-row">
              <select value={room} onChange={(e) => setRoom(e.target.value)}>{ROOMS.map((r) => <option key={r}>{r}</option>)}</select>
              <label className="btn small">{busy ? '…' : `📷 ${ko ? '추가' : 'Add'}`}<input type="file" multiple accept="image/*,video/*" hidden onChange={(e) => upload(e.target.files)} /></label>
              <span className="small muted">{ko ? 'GPS·EXIF 제거, 얼굴 흐림, 영상은 최대 6장면' : 'GPS/EXIF removed, faces blurred, up to 6 frames per video'}</span>
            </div>
            {insp.videos.map((v) => (
              <div key={v.id} className="video">
                <video src={fileUrl(v.id, v.sha256)} controls muted playsInline preload="metadata" />
                <div className="small muted">🎬 {v.name} · {String(v.meta.duration_s ?? '?')}s</div>
              </div>
            ))}
            {byRoom.map(([r, evs]) => (
              <div key={r} className="room">
                <h5>{r}</h5>
                <div className="thumbs">{evs.map((e) => <EvidenceThumb key={e.id} ev={e} onOpen={setOpen} />)}</div>
              </div>
            ))}
          </Disclosure>
        </Card>
      )}
      <EvidenceModal ev={open} onClose={() => setOpen(null)} />
    </div>
  )
}
