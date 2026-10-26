/** Thin wrapper around the Rentrail JSON API (same origin; the session lives in an HttpOnly cookie). */

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T,>(path: string) => fetch(path, { credentials: 'same-origin' }).then((r) => handle<T>(r)),
  post: <T,>(path: string, body?: unknown) =>
    fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    }).then((r) => handle<T>(r)),
  patch: <T,>(path: string, body: unknown) =>
    fetch(path, {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => handle<T>(r)),
  del: <T,>(path: string) => fetch(path, { method: 'DELETE', credentials: 'same-origin' }).then((r) => handle<T>(r)),
  upload: <T,>(path: string, form: FormData) =>
    fetch(path, { method: 'POST', credentials: 'same-origin', body: form }).then((r) => handle<T>(r)),
}

/** The fingerprint in the URL makes the browser fetch a new picture whenever the file behind an id changes. */
export const fileUrl = (id: number, sha?: string) => `/api/files/${id}${sha ? `?v=${sha.slice(0, 12)}` : ''}`

export const money = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export const usd = (n: number | null | undefined, digits = 4) =>
  n === null || n === undefined ? '—' : `$${Number(n).toFixed(digits)}`

export const num = (n: number | null | undefined) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('en-US'))

export const fmtDate = (iso: string | null | undefined, lang: 'en' | 'ko' = 'en') => {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(lang === 'ko' ? 'ko-KR' : 'en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

/** A run started by the chatbot, handed to the page it opens (so that page shows it live). */
export function giveFocus(page: string, runId: number) {
  sessionStorage.setItem('rentrail_focus', JSON.stringify({ page, runId }))
}
export function takeFocus(page: string): number | null {
  const raw = sessionStorage.getItem('rentrail_focus')
  if (!raw) return null
  try {
    const f = JSON.parse(raw) as { page: string; runId: number }
    if (f.page !== page) return null
    sessionStorage.removeItem('rentrail_focus')
    return f.runId
  } catch {
    return null
  }
}
