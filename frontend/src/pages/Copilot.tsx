import ChatPanel from '../components/ChatPanel'
import { PageHead } from '../components/ui'
import { useApp } from '../i18n'

export default function Copilot() {
  const { lang } = useApp()
  const ko = lang === 'ko'
  return (
    <div>
      <PageHead
        title={ko ? '대법관 댄에게 묻기' : 'Ask Chief Justice Dan'}
        sub={ko ? '답하고, 팀원에게 묻고, 페이지 이동과 작업까지 해 줍니다.' : 'Answers, asks teammates, opens pages and runs tasks for you.'}
        agent="judge"
        color="#4f46e5"
      />
      <div className="card">
        <ChatPanel variant="page" page="copilot" />
      </div>
    </div>
  )
}
