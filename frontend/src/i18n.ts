import { createContext, useContext } from 'react'
import type { Agent, Lang, Me } from './types'

const STRINGS = {
  tagline: ['Every lease leaves a trail.', '모든 임대에는 기록이 남습니다.'],
  pitch: [
    'A tenant-side AI team for first-time U.S. renters in Connecticut: it reads your lease, records the condition of your home in photos and video, keeps every deadline, protects both sides of a sublet, and fights unfair deposit deductions with evidence.',
    '미국 렌트가 처음인 코네티컷 세입자를 위한 세입자 편 AI 팀입니다. 계약서를 읽고, 사진·영상으로 집 상태를 기록하고, 모든 기한을 챙기고, 서브렛 양쪽을 지키고, 부당한 보증금 공제에 증거로 맞섭니다.',
  ],
  home: ['Home', '홈'],
  lease: ['Lease', '계약서'],
  evidence: ['Inspections', '점검'],
  court: ['Deposit', '보증금'],
  sublet: ['Sublet', '서브렛'],
  bills: ['Bills', '공과금·보험'],
  copilot: ['Ask Chief Justice Dan', '대법관 댄에게 묻기'],
  agents: ['Agents', '에이전트'],
  safety: ['Safety', '안전'],
  community: ['Community', '커뮤니티'],
  section_record: ['My home', '내 집'],
  section_money: ['Money', '돈'],
  section_help: ['People', '사람들'],
  section_inside: ['Under the hood', '시스템'],
  logout: ['Log out', '로그아웃'],
  today: ['Today', '오늘'],
  demo_date: ['Demo date (time machine)', '데모 날짜 (타임머신)'],
  tokens_today: ['Tokens today', '오늘 사용 토큰'],
  run: ['Run', '실행'],
  rerun: ['Run again', '다시 실행'],
  running: ['Working…', '작업 중…'],
  upload: ['Upload', '업로드'],
  pages: ['pages', '쪽'],
  page: ['p.', 'p.'],
  not_legal: ['Information, not legal advice. Connecticut law only.', '법률 자문이 아닌 정보입니다. 코네티컷 법만 다룹니다.'],
  upcoming: ['Upcoming deadlines', '다가오는 기한'],
  overdue: ['overdue', '지남'],
  days_left: ['days left', '일 남음'],
  done: ['Done', '완료'],
  your_bench: ['Your bulldog bench', '나의 불독 팀'],
  trail: ['Your lease trail', '나의 임대 기록'],
  login: ['Log in', '로그인'],
  register: ['Create account', '계정 만들기'],
  email: ['Email', '이메일'],
  password: ['Password', '비밀번호'],
  name: ['Name', '이름'],
  try_demo: ['Try the demo', '데모 체험'],
  demo_alex: ['Alex — tenant (sublets in summer)', 'Alex — 세입자 (여름에 서브렛)'],
  demo_jordan: ['Jordan — summer subtenant', 'Jordan — 여름 서브렛 세입자'],
  live_trace: ['Live agent trace', '실시간 에이전트 기록'],
  input: ['Input', '입력'],
  output: ['Output', '출력'],
  cost: ['Cost', '비용'],
  findings: ['Findings', '발견된 하자'],
  no_findings: ['No damage found.', '하자 없음'],
  possible: ['Possible (low confidence — confirm yourself)', '가능성 (신뢰도 낮음 — 직접 확인)'],
  fingerprint: ['Fingerprint (SHA-256)', '파일 지문 (SHA-256)'],
  verify: ['Verify', '검증'],
  intact: ['Intact — matches the upload', '원본과 일치'],
}

export type Key = keyof typeof STRINGS

export function translate(lang: Lang, key: Key): string {
  return STRINGS[key][lang === 'ko' ? 1 : 0]
}

/** Pick `x_en` / `x_ko` from an object for the current language. */
export function pick(obj: Record<string, unknown> | null | undefined, base: string, lang: Lang): string {
  if (!obj) return ''
  const v = obj[`${base}_${lang}`] ?? obj[`${base}_en`] ?? obj[base]
  return typeof v === 'string' ? v : ''
}

export interface AppState {
  lang: Lang
  me: Me | null
  roster: Agent[]
  t: (key: Key) => string
  refreshMe: () => Promise<void>
  go: (page: string) => void
  bump: number
  setBump: (fn: (n: number) => number) => void
}

export const AppCtx = createContext<AppState>(null as unknown as AppState)
export const useApp = () => useContext(AppCtx)
