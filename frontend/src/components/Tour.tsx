/** "Alex's year" guided tour: each step moves the time machine, switches the role and opens a page,
 * so a first-time visitor sees the whole story in about two minutes. No AI calls. */

import { useEffect, useRef } from 'react'
import { fmtDate } from '../api'
import { useApp } from '../i18n'
import type { User } from '../types'
import Bulldog from './Bulldog'

interface Step {
  date: string; mode: User['mode']; page: string; costume: Parameters<typeof Bulldog>[0]['costume']; color: string
  title_en: string; title_ko: string; text_en: string; text_ko: string
}

export const TOUR: Step[] = [
  { date: '2026-08-01', mode: 'tenant', page: 'home', costume: 'judge', color: '#4f46e5',
    title_en: 'Meet Alex', title_ko: 'Alex를 소개합니다',
    text_en: 'A Yale student on day 1 of a 12-month lease in New Haven. Home shows what is next, money due, and the Deposit Shield.',
    text_ko: '뉴헤이븐에서 12개월 임대 첫날을 맞은 Yale 학생입니다. 홈에는 다음 할 일, 낼 돈, 보증금 방패가 보입니다.' },
  { date: '2026-08-01', mode: 'tenant', page: 'lease', costume: 'clerk', color: '#3b82f6',
    title_en: 'The lease, in tiles', title_ko: '계약서를 한눈에',
    text_en: 'Clerk Dan read the lease: key numbers, every deadline, and terms to watch — each with its page number.',
    text_ko: '서기관 댄이 계약서를 읽고 핵심 숫자·모든 기한·주의할 조항을 쪽수와 함께 정리했습니다.' },
  { date: '2026-08-01', mode: 'tenant', page: 'inspections', costume: 'detective', color: '#f97316',
    title_en: 'A clean move-in, on record', title_ko: '깨끗한 입주, 기록으로',
    text_en: 'Photos and a walkthrough video. The Checkpoint strips GPS, blurs faces and fingerprints every file; Detective Dan finds no damage.',
    text_ko: '사진과 둘러보기 영상. 검문소가 GPS를 지우고 얼굴을 흐리고 파일마다 지문을 남깁니다. 형사 댄은 하자 없음으로 판단했습니다.' },
  { date: '2026-09-10', mode: 'tenant', page: 'bills', costume: 'treasurer', color: '#22c55e',
    title_en: 'First bills', title_ko: '첫 고지서',
    text_en: 'Treasurer Dan reads each bill and the renter’s insurance and checks them against the lease.',
    text_ko: '회계관 댄이 고지서와 세입자 보험을 읽고 계약서와 대조합니다.' },
  { date: '2027-05-12', mode: 'sublessor', page: 'sublet', costume: 'sheriff', color: '#eab308',
    title_en: 'Summer sublet', title_ko: '여름 서브렛',
    text_en: 'Alex sublets to Jordan. Sheriff Dan drafted the consent letter and sublease; Jordan’s $1,500 deposit sits in Rentrail escrow, not in anyone’s pocket.',
    text_ko: 'Alex가 Jordan에게 서브렛을 줍니다. 보안관 댄이 동의서와 계약서를 쓰고, Jordan의 보증금 $1,500은 개인이 아닌 Rentrail 에스크로에 있습니다.' },
  { date: '2027-06-01', mode: 'sublessor', page: 'inspections', costume: 'detective', color: '#f97316',
    title_en: 'Hand-off', title_ko: '인계',
    text_en: 'Alex’s own floor gouge and hallway chip are recorded at hand-off, so Jordan can never be blamed for them.',
    text_ko: 'Alex가 만든 바닥 패임과 복도 벽 찍힘이 인계 때 기록되어, Jordan이 책임질 일이 없습니다.' },
  { date: '2027-07-29', mode: 'sublessor', page: 'court', costume: 'lawyer', color: '#a855f7',
    title_en: 'NEW: fix it or pay for it?', title_ko: '새 기능: 고칠까, 물어줄까?',
    text_en: 'Two days before move-out, the precheck prices each damage: patch the chip yourself for $12, hire a pro for the floor, and claim Jordan’s crack from the escrow.',
    text_ko: '퇴거 이틀 전, 퇴거 전 진단이 하자마다 값을 매깁니다: 벽 찍힘은 $12로 직접, 바닥은 업체에, Jordan의 균열은 에스크로에서 청구.' },
  { date: '2027-07-30', mode: 'sublessor', page: 'sublet', costume: 'sheriff', color: '#eab308',
    title_en: 'Escrow settlement', title_ko: '에스크로 정산',
    text_en: 'Only Jordan’s crack ($150 held until a repair invoice) and his electricity share ($88.10, computed by code) are deducted. The rest goes back to Jordan.',
    text_ko: 'Jordan의 균열($150, 수리 영수증이 올 때까지 보류)과 전기요금 분담($88.10, 코드 계산)만 공제되고 나머지는 Jordan에게 돌아갑니다.' },
  { date: '2027-08-25', mode: 'tenant', page: 'court', costume: 'judge', color: '#4f46e5',
    title_en: 'Deposit court', title_ko: '보증금 법정',
    text_en: 'The landlord’s statement came 3 days late and hid text aimed at the AI. The Checkpoint removed it; Counsel and the Chief Justice cut the claims to fair amounts and wrote the letter.',
    text_ko: '집주인 내역서는 3일 늦게 왔고 AI를 노린 숨은 글이 있었습니다. 검문소가 제거했고, 변호사와 대법관 댄이 금액을 공정하게 줄이고 레터를 썼습니다.' },
  { date: '2027-08-25', mode: 'tenant', page: 'agents', costume: 'judge', color: '#4f46e5',
    title_en: 'Under the hood', title_ko: '내부 구조',
    text_en: 'Every step was a traced run: who called whom, real token counts and cost. A full year costs about three cents.',
    text_ko: '모든 단계가 기록된 실행입니다: 누가 누구를 불렀는지, 실제 토큰 수와 비용. 1년 전체가 약 3센트입니다.' },
  { date: '2027-08-25', mode: 'tenant', page: 'safety', costume: 'gate', color: '#00356b',
    title_en: 'Safety', title_ko: '안전',
    text_en: 'Run the self-test: hidden PDF text, instructions inside photos, personal data — blocked before any AI reads them. Tour done — try the 🕰️ time machine or ask Dan (bottom right).',
    text_ko: '자체 테스트를 실행해 보세요: 숨은 PDF 글씨, 사진 속 지시문, 개인정보가 AI보다 먼저 차단됩니다. 투어 끝 — 🕰️ 타임머신을 돌려보거나 오른쪽 아래 댄에게 물어보세요.' },
]

export default function Tour({ step, setStep, apply }: {
  step: number; setStep: (n: number | null) => void; apply: (s: Step) => Promise<void>
}) {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const s = TOUR[step]
  const applied = useRef<number | null>(null)
  useEffect(() => {
    if (applied.current === step) return
    applied.current = step
    apply(s)
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="tour" role="dialog" aria-label="Tour">
      <div className="tour-head">
        <Bulldog costume={s.costume} furColor={s.color} size={44} />
        <div className="grow">
          <div className="small muted">{ko ? '투어' : 'Tour'} {step + 1}/{TOUR.length} · 🕰️ {fmtDate(s.date, lang)}</div>
          <strong>{ko ? s.title_ko : s.title_en}</strong>
        </div>
        <button className="modal-x static" onClick={() => setStep(null)} aria-label="close">×</button>
      </div>
      <p className="small">{ko ? s.text_ko : s.text_en}</p>
      <div className="tour-dots">{TOUR.map((_, i) => <span key={i} className={i === step ? 'on' : i < step ? 'past' : ''} onClick={() => setStep(i)} />)}</div>
      <div className="row gap tour-btns">
        <button className="btn ghost small" disabled={step === 0} onClick={() => setStep(step - 1)}>← {ko ? '이전' : 'Back'}</button>
        {step < TOUR.length - 1
          ? <button className="btn primary small" onClick={() => setStep(step + 1)}>{ko ? '다음' : 'Next'} →</button>
          : <button className="btn primary small" onClick={() => setStep(null)}>{ko ? '끝내기' : 'Finish'} ✓</button>}
      </div>
    </div>
  )
}
