import { useEffect, useState } from 'react'
import { api, fmtDate } from '../api'
import Bulldog from '../components/Bulldog'
import RunPanel, { useRun } from '../components/RunPanel'
import { Card, Err, Markdownish, PageHead, Pill } from '../components/ui'
import { useApp } from '../i18n'

interface Post {
  id: number; category: 'review' | 'qa' | 'story'; title: string; body: string; building: string; rating: number | null
  author: string; created_at: string; likes: number; comments: number; liked?: number
}
interface Comment { id: number; body: string; is_ai: number; author: string | null; created_at: string }

const CATS: { id: 'all' | Post['category']; en: string; ko: string; icon: string }[] = [
  { id: 'all', en: 'All', ko: '전체', icon: '🗂️' },
  { id: 'review', en: 'Reviews', ko: '리뷰', icon: '⭐' },
  { id: 'qa', en: 'Q&A', ko: 'Q&A', icon: '❓' },
  { id: 'story', en: 'Stories', ko: '후기', icon: '📖' },
]

export default function Community() {
  const { lang } = useApp()
  const ko = lang === 'ko'
  const [cat, setCat] = useState<'all' | Post['category']>('all')
  const [posts, setPosts] = useState<Post[]>([])
  const [sel, setSel] = useState<(Omit<Post, 'comments'> & { comments: Comment[] }) | null>(null)
  const [comment, setComment] = useState('')
  const [writing, setWriting] = useState(false)
  const [draft, setDraft] = useState({ category: 'review', title: '', body: '', building: '', rating: 5 })
  const [error, setError] = useState<string | null>(null)
  const [runId, setRunId] = useState<number | null>(null)

  const load = () => api.get<Post[]>(`/api/posts${cat === 'all' ? '' : `?category=${cat}`}`).then(setPosts)
  useEffect(() => {
    load()
  }, [cat])
  const openPost = async (id: number) => setSel(await api.get<Omit<Post, 'comments'> & { comments: Comment[] }>(`/api/posts/${id}`))
  const run = useRun(runId, () => sel && openPost(sel.id))

  const submit = async () => {
    try {
      setError(null)
      const r = await api.post<{ id: number; masked: Record<string, number> }>('/api/posts', draft)
      setWriting(false)
      setDraft({ category: 'review', title: '', body: '', building: '', rating: 5 })
      await load()
      openPost(r.id)
      if (Object.keys(r.masked).length) setError(ko ? '전화번호·이메일 등 개인정보는 자동으로 가려졌습니다.' : 'Phone numbers, emails and account numbers were hidden automatically.')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div>
      <PageHead
        title={ko ? '커뮤니티: 리뷰 · Q&A · 후기' : 'Community: reviews, Q&A, stories'}
        sub={ko ? 'Yale 세입자들의 리뷰·질문·후기. 개인정보는 자동으로 가려집니다.' : 'Reviews, questions and stories from Yale renters. Personal details are hidden automatically.'}
        agent="lawyer"
        color="#a855f7"
      />
      <div className="row gap">
        <div className="tabs">
          {CATS.map((c) => <button key={c.id} className={cat === c.id ? 'on' : ''} onClick={() => setCat(c.id)}>{c.icon} {ko ? c.ko : c.en}</button>)}
        </div>
        <button className="btn primary" onClick={() => setWriting(!writing)}>✍️ {ko ? '글쓰기' : 'Write a post'}</button>
      </div>
      <Err error={error} />
      {writing && (
        <Card title={ko ? '새 글' : 'New post'}>
          <div className="form-grid">
            <label>{ko ? '종류' : 'Type'}
              <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                <option value="review">{ko ? '리뷰' : 'Review'}</option><option value="qa">Q&A</option><option value="story">{ko ? '후기' : 'Story'}</option>
              </select>
            </label>
            {draft.category === 'review' && (
              <>
                <label>{ko ? '건물/지역' : 'Building / area'}<input value={draft.building} onChange={(e) => setDraft({ ...draft, building: e.target.value })} /></label>
                <label>{ko ? '별점' : 'Rating'}<select value={draft.rating} onChange={(e) => setDraft({ ...draft, rating: Number(e.target.value) })}>{[5, 4, 3, 2, 1].map((n) => <option key={n}>{n}</option>)}</select></label>
              </>
            )}
          </div>
          <label>{ko ? '제목' : 'Title'}<input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
          <label>{ko ? '내용' : 'Text'}<textarea rows={5} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} /></label>
          <button className="btn primary" onClick={submit}>{ko ? '올리기' : 'Post'}</button>
        </Card>
      )}
      <div className="split">
        <div className="split-left">
          {posts.map((p) => (
            <button key={p.id} className={`post ${sel?.id === p.id ? 'on' : ''}`} onClick={() => openPost(p.id)}>
              <div className="row gap">
                <Pill tone={p.category === 'review' ? 'amber' : p.category === 'qa' ? 'purple' : 'blue'}>{CATS.find((c) => c.id === p.category)![ko ? 'ko' : 'en']}</Pill>
                {p.rating ? <span className="stars">{'★'.repeat(p.rating)}{'☆'.repeat(5 - p.rating)}</span> : null}
              </div>
              <strong>{p.title}</strong>
              <div className="small muted">{p.author} · {fmtDate(p.created_at, lang)} · ♥ {p.likes} · 💬 {p.comments}</div>
            </button>
          ))}
        </div>
        <div className="split-right">
          {sel ? (
            <Card title={sel.title} right={<Pill tone="gray">{sel.author}</Pill>}>
              {sel.building && <p className="small muted">🏢 {sel.building} {sel.rating ? <span className="stars">{'★'.repeat(sel.rating)}</span> : null}</p>}
              <p className="post-body">{sel.body}</p>
              <div className="row gap">
                <button className="btn ghost small" onClick={async () => { await api.post(`/api/posts/${sel.id}/like`); openPost(sel.id); load() }}>♥ {ko ? '좋아요' : 'Like'}</button>
                {sel.category === 'qa' && (
                  <button className="btn small" disabled={run?.status === 'running'} onClick={async () => setRunId((await api.post<{ run_id: number }>(`/api/posts/${sel.id}/ask-dan`)).run_id)}>
                    ⚖️ {ko ? '변호사 댄에게 답 요청' : 'Ask Counsel Dan'}
                  </button>
                )}
              </div>
              <RunPanel run={run} compact />
              <div className="comments">
                {sel.comments.map((c) => (
                  <div key={c.id} className={`comment ${c.is_ai ? 'ai' : ''}`}>
                    {c.is_ai ? <Bulldog costume="lawyer" furColor="#a855f7" size={34} /> : <span className="avatar">{(c.author ?? '?')[0]}</span>}
                    <div>
                      <div className="small muted">{c.is_ai ? (ko ? '변호사 댄 (AI · 법률 자문 아님)' : 'Counsel Dan (AI · not legal advice)') : c.author} · {fmtDate(c.created_at, lang)}</div>
                      <Markdownish text={c.body} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="row gap">
                <input className="grow" value={comment} onChange={(e) => setComment(e.target.value)} placeholder={ko ? '댓글 쓰기' : 'Write a comment'} />
                <button className="btn" onClick={async () => { if (!comment.trim()) return; setSel(await api.post(`/api/posts/${sel.id}/comments`, { body: comment })); setComment(''); load() }}>{ko ? '등록' : 'Reply'}</button>
              </div>
            </Card>
          ) : <div className="empty">{ko ? '글을 선택하세요.' : 'Pick a post.'}</div>}
        </div>
      </div>
    </div>
  )
}
