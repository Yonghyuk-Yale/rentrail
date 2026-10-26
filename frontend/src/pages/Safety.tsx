import { useEffect, useState } from 'react'
import { api, fmtDate } from '../api'
import { Card, PageHead, Pill } from '../components/ui'
import { useApp } from '../i18n'

interface Event { id: number; kind: string; detail: unknown; created_at: string; run_id: number | null }
interface TestCase { name: string; passed: boolean; detail: unknown; ms: number }

const KIND: Record<string, [string, string, string]> = {
  hidden_text_removed: ['🕵️', 'Hidden text removed from a document', '문서의 숨은 글씨 제거'],
  instruction_text_flagged: ['⚠️', 'Instruction-like text flagged in a document', '문서 속 지시문 감지'],
  instruction_in_image: ['🛡️', 'Text addressed to the AI found in a photo/video — ignored', '사진·영상 속 AI 지시 글씨 — 무시'],
  chat_instruction_flagged: ['💬', 'Instruction-like text in chat', '대화 속 지시문 감지'],
  pii_masked: ['🙈', 'Personal data masked before the model', '개인정보를 AI 전에 가림'],
  exif_removed: ['📍', 'Photo metadata (GPS) removed', '사진 메타데이터(GPS) 제거'],
  faces_blurred: ['😶', 'Faces blurred', '얼굴 흐림 처리'],
  budget_block: ['💸', 'Token budget stopped a run', '토큰 한도로 실행 중단'],
}

export default function Safety() {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const [events, setEvents] = useState<Event[]>([])
  const [tests, setTests] = useState<{ passed: number; total: number; cases: TestCase[] } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.get<Event[]>('/api/safety').then(setEvents)
  }, [])
  const counts = events.reduce<Record<string, number>>((m, e) => ({ ...m, [e.kind]: (m[e.kind] ?? 0) + 1 }), {})

  return (
    <div>
      <PageHead
        title={ko ? '안전 센터' : 'Safety Center'}
        sub={ko ? '모든 입력이 지나가는 검문소(코드)가 실제로 막은 것과 자체 테스트.' : 'What the always-on checkpoint (plain code) blocked, plus a one-click self-test.'}
        agent="gate"
        color="#ef4444"
      />
      <div className="grid3">
        {[
          ['🧱', ko ? '공격' : 'Attacks', ko ? '숨은 흰 글씨 제거, 문서·사진 속 지시문은 증거로만 취급, 법 조항·쪽수·증거 번호 검증' : 'Hidden-text removal, instructions in documents/photos treated as evidence only, law/page/evidence ids validated'],
          ['🧭', ko ? '오작동' : 'Malfunction', ko ? '날짜·금액은 코드가 계산, 공제 승인은 청구액을 넘지 못함, 낮은 신뢰도 발견은 "가능성"으로 분리, 큰 금액은 사람 검토 표시' : 'Dates and dollars computed by code, approvals capped at the claim, low-confidence findings kept apart, large amounts flagged for human review'],
          ['💸', ko ? '과다 지출' : 'Overspending', ko ? '실행당 15만, 계정당 하루 80만 토큰 한도. 모델 호출마다 확인' : '150k tokens per run and 800k per account per day, checked before every model call'],
          ['🔐', ko ? '개인정보' : 'Privacy', ko ? '사진 GPS·EXIF 제거, 얼굴 흐림, 이름·주소·계좌 가림, 파일 암호화 저장, 비밀번호 해시' : 'Photo GPS/EXIF stripped, faces blurred, names/addresses/accounts masked, files encrypted, passwords hashed'],
        ].map(([i, h, p]) => (
          <Card key={h} title={`${i} ${h}`}><p className="small">{p}</p></Card>
        ))}
      </div>
      <Card title={ko ? '자체 테스트 (AI 호출 없음, 비용 0)' : 'Self-test (no AI calls, $0)'} right={
        <button className="btn primary" disabled={busy} onClick={async () => { setBusy(true); setTests(await api.post('/api/safety/selftest')); setBusy(false) }}>▶ {ko ? '실행' : 'Run self-test'}</button>
      }>
        {tests && (
          <>
            <p><strong className={tests.passed === tests.total ? 'ok' : 'bad'}>{tests.passed} / {tests.total} {ko ? '통과' : 'passed'}</strong></p>
            {tests.cases.map((c) => (
              <details key={c.name} className="test">
                <summary>{c.passed ? '✅' : '❌'} {c.name} <span className="muted small">{c.ms} ms</span></summary>
                <pre>{JSON.stringify(c.detail, null, 2)}</pre>
              </details>
            ))}
          </>
        )}
      </Card>
      <Card title={ko ? '실제로 막은 기록' : 'What the Checkpoint actually blocked'} right={
        <span>{Object.entries(counts).map(([k, n]) => <Pill key={k} tone="gray">{KIND[k]?.[0] ?? '•'} {n}</Pill>)}</span>
      }>
        <table className="tbl">
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td className="small">{fmtDate(e.created_at, lang)}</td>
                <td>{KIND[e.kind]?.[0]} {KIND[e.kind]?.[ko ? 2 : 1] ?? e.kind}</td>
                <td><pre className="small inline">{JSON.stringify(e.detail)}</pre></td>
                <td className="small muted">{e.run_id ? `run #${e.run_id}` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
