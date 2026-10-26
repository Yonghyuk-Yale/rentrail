export type Lang = 'en' | 'ko'

export interface User {
  id: number
  email: string
  name: string
  lang: Lang
  demo_today: string | null
  is_demo: number
  mode: 'tenant' | 'sublessor' | 'subtenant'
}

export interface Me {
  user: User
  today: string
  tokens_today: number
  daily_limit: number
}

export interface Agent {
  id: string
  name: string
  name_ko: string
  costume: Costume
  color: string
  role_en: string
  role_ko: string
  llm: boolean
}

export type Costume = 'judge' | 'clerk' | 'detective' | 'lawyer' | 'sheriff' | 'treasurer' | 'police' | 'gate' | 'plain'

export interface AgentCall {
  id: number
  seq: number
  agent: string
  caller: string
  purpose: string
  input_preview: string
  output: unknown
  input_tokens: number
  cached_tokens: number
  output_tokens: number
  requests: number
  cost_usd: number
  ms: number | null
  status: string
  created_at: string
}

export interface Run {
  id: number
  kind: string
  title: string
  status: 'running' | 'done' | 'failed'
  started_at: string
  finished_at: string | null
  input_tokens: number
  cached_tokens: number
  output_tokens: number
  cost_usd: number
  error: string | null
  ref: string | null
  result?: unknown
  calls?: AgentCall[]
  total_tokens?: number
}

export interface Clause {
  key: string
  title_en: string
  title_ko: string
  plain_en: string
  plain_ko: string
  page: number | null
  quote: string
  importance: 'high' | 'medium' | 'low'
}

export interface LeaseCard {
  lease_start: string | null
  lease_end: string | null
  monthly_rent: number | null
  security_deposit: number | null
  rent_due_day: number | null
  late_fee_text: string | null
  inventory_form_hours: number | null
  move_out_notice_days: number | null
  auto_renews: boolean | null
  sublet_requires_consent: boolean | null
  sublet_terms_en: string | null
  insurance_required: boolean | null
  insurance_min_liability: number | null
  repair_request_method: string | null
  utilities: { service: string; paid_by: string; billed_by: string; page: number | null }[]
  clauses: Clause[]
  red_flags: { title_en: string; title_ko: string; why_en: string; why_ko: string; page: number | null }[]
  summary_en: string
  summary_ko: string
}

export interface Lease {
  id: number
  title: string
  file_id: number
  page_count: number | null
  card: LeaseCard | null
  analysis_meta: Record<string, unknown>
  run_id: number | null
}

export interface Finding {
  evidence_id: number
  room: string
  item: string
  location: string
  damage_type: string
  severity: 1 | 2 | 3
  description_en: string
  description_ko: string
  confidence: number
}

export interface Evidence {
  id: number
  file_id: number
  parent_file_id: number | null
  room: string
  label: string
  t_seconds: number | null
  mime: string
  sha256: string
  uploaded_at: string
  meta: Record<string, unknown>
}

export interface InspectionResult {
  findings: Finding[]
  possible?: Finding[]
  seen_text: { evidence_id: number; text: string; looks_like_instruction: boolean; blocked?: boolean }[]
  checked_evidence_ids: number[]
  overall_en: string
  overall_ko: string
  injection_blocked?: boolean
}

export interface Inspection {
  id: number
  user_id: number
  lease_id: number | null
  sublet_id: number | null
  kind: 'move_in' | 'move_out' | 'sublet_handoff' | 'sublet_return'
  title: string
  inspected_on: string
  status: string
  result: InspectionResult | null
  run_id: number | null
  evidence: Evidence[]
  videos: { id: number; name: string; meta: Record<string, unknown>; sha256: string }[]
}

export interface ComparedItem {
  move_out_index: number
  status: 'pre_existing' | 'new_damage' | 'wear_and_tear' | 'unclear'
  matched_move_in_index: number | null
  earlier_evidence_id: number | null
  reason_en: string
  reason_ko: string
  confidence: number
  later: Finding
  earlier: Finding | null
}

export interface Comparison {
  items: ComparedItem[]
  summary_en: string
  summary_ko: string
}

export interface Task {
  key: string
  date: string | null
  category: string
  title_en: string
  title_ko: string
  law_id: string | null
  detail_en: string
  detail_ko: string
  page: number | null
  done: boolean
  days_left: number | null
  amount: number | null
}
