/** Utility shares during a sublet: which of the sublessor's bills overlap the sublet, the pro-rated
 * share (computed by code from days), and whether the subtenant has paid it (simulated payment). */

import { useEffect, useState } from 'react'
import { api, fmtDate, money } from '../api'
import { useApp } from '../i18n'
import { Card, Err, Pill } from './ui'

export interface Share {
  bill_id: number
  service: string
  provider: string
  period: string
  amount: number
  overlap_days: number
  period_days: number
  subtenant_share: number
  due: string | null
  paid_on: string | null
}
interface SubletLite { id: number; role: 'sublessor' | 'subtenant'; utility_shares: Share[]; sublease: { utilities: { service: string; paid_by: string }[] } | null }

export default function UtilityShares() {
  const { lang, me } = useApp()
  const ko = lang === 'ko'
  const [s, setS] = useState<SubletLite | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = () => api.get<SubletLite[]>('/api/sublets').then((l) => setS(l[0] ?? null))
  useEffect(() => {
    load()
  }, [])
  if (!s) return null
  const pay = async (bill_id: number) => {
    setError(null)
    try {
      setS(await api.post<SubletLite>(`/api/sublets/${s.id}/pay-utility`, { bill_id, method: 'card', card_number: '4242424242424242' }))
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const terms = s.sublease?.utilities ?? []
  return (
    <Card title={`🔌 ${ko ? '서브렛 기간 공과금 분담' : 'Utility shares during the sublet'}`}>
      <p className="small muted">
        {ko
          ? '서브렛 계약서 기준: 전기는 원 세입자 명의로 두고, 서브렛 세입자가 사용 일수만큼 10일 안에 돌려줍니다. 나머지는 월세에 포함됩니다.'
          : 'Per the sublease: electricity stays in the sublessor’s name and the subtenant reimburses the days they lived there within 10 days; the rest is included in rent.'}
      </p>
      {terms.length > 0 && (
        <div className="small">{terms.map((u) => <Pill key={u.service} tone={u.paid_by === 'tenant' ? 'amber' : 'gray'}>{u.service}: {u.paid_by === 'tenant' ? (ko ? '세입자 분담' : 'subtenant shares') : (ko ? '포함' : 'included')}</Pill>)}</div>
      )}
      <Err error={error} />
      {s.utility_shares.length === 0 ? (
        <p className="muted small-top">{ko ? '아직 서브렛 기간이 포함된 고지서가 없습니다.' : 'No bill covering the sublet period has arrived yet.'}</p>
      ) : (
        <table className="tbl small-top">
          <thead>
            <tr>
              <th>{ko ? '항목' : 'Service'}</th><th>{ko ? '청구 기간' : 'Bill period'}</th>
              <th className="num">{ko ? '고지 금액' : 'Bill'}</th><th className="num">{ko ? '일수' : 'Days'}</th>
              <th className="num">{ko ? '분담액' : 'Share'}</th><th>{ko ? '기한' : 'Due'}</th><th />
            </tr>
          </thead>
          <tbody>
            {s.utility_shares.map((x) => (
              <tr key={x.bill_id}>
                <td>{x.provider} · {x.service}</td>
                <td className="small">{x.period}</td>
                <td className="num">{money(x.amount)}</td>
                <td className="num">{x.overlap_days}/{x.period_days}</td>
                <td className="num"><strong>{money(x.subtenant_share)}</strong></td>
                <td className="nowrap">{fmtDate(x.due, lang)}</td>
                <td>
                  {x.paid_on ? <Pill tone="green">✓ {ko ? '납부' : 'paid'} {fmtDate(x.paid_on, lang)}</Pill>
                    : s.role === 'subtenant' ? <button className="btn small primary" onClick={() => pay(x.bill_id)}>{ko ? '가상 결제' : 'Pay (simulated)'}</button>
                      : <Pill tone="amber">{ko ? '미납 — 정산 때 보증금에서 공제' : 'unpaid — deducted at settlement'}</Pill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {me?.user.mode === 'subtenant' && <p className="small muted">{ko ? '미납 분담액은 정산 때 보증금에서 빠집니다.' : 'Unpaid shares are taken from the deposit at settlement.'}</p>}
    </Card>
  )
}
