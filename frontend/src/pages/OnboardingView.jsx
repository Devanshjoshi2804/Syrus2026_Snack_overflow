import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api, SessionSocket } from '../api/client'
import { ChatFeed } from '../components/ChatFeed'
import { ChatInput } from '../components/ChatInput'
import { TaskPanel } from '../components/TaskPanel'
import { PhaseBar } from '../components/PhaseBar'
import { ChecklistModal } from '../components/ChecklistModal'
import { IntegrationBadge } from '../components/IntegrationBadge'
import styles from './OnboardingView.module.css'

export function OnboardingView() {
  const { sessionId } = useParams()
  const [dashboard, setDashboard] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [initError, setInitError] = useState('')
  const [showChecklist, setShowChecklist] = useState(false)
  const socketRef = useRef(null)

  useEffect(() => {
    api.getSession(sessionId)
      .then((data) => {
        const { messages: msgs, ...rest } = data
        setDashboard(rest)
        setMessages(msgs || [])
      })
      .catch((err) => setInitError(err.message))
  }, [sessionId])

  useEffect(() => {
    const sock = new SessionSocket(sessionId, (data) => {
      setDashboard((prev) => ({ ...prev, ...data }))
    })
    sock.connect()
    socketRef.current = sock
    return () => sock.close()
  }, [sessionId])

  const sendMessage = useCallback(async (content) => {
    const trimmed = content.trim()

    // Shell command: prefix with $ to run in the E2B sandbox
    if (trimmed.startsWith('$')) {
      const cmd = trimmed.slice(1).trim()
      if (!cmd) return
      setLoading(true)
      setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
      try {
        const { command, output, returncode } = await api.runTerminal(sessionId, cmd)
        setMessages((prev) => [
          ...prev,
          {
            role: 'terminal',
            content: `$ ${command}\n${output}`,
            success: returncode === 0,
          },
        ])
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `[Error: ${err.message}]` },
        ])
      } finally {
        setLoading(false)
      }
      return
    }

    setLoading(true)
    setMessages((prev) => [...prev, { role: 'user', content }])
    try {
      const { messages: updated } = await api.sendMessage(sessionId, content)
      setMessages(updated)
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `[Error: ${err.message}]` },
      ])
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  const sendAction = useCallback(async (action) => {
    setLoading(true)
    try {
      const {
        reply,
        dashboard: updated,
        agentTranscript,
        agentSuccess,
        executedTaskId,
      } = await api.sendAction(sessionId, action)
      setDashboard((prev) => ({ ...prev, ...updated }))

      const newMessages = [
        { role: 'user', content: `[action: ${action}]` },
      ]

      // Inject inline terminal block for every agent run (success or blocked)
      if (action === 'watch_agent' && agentTranscript) {
        newMessages.push({
          role: 'terminal',
          content: agentTranscript,
          taskId: executedTaskId,
          success: agentSuccess,
        })
      }

      newMessages.push({ role: 'assistant', content: reply })
      setMessages((prev) => [...prev, ...newMessages])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `[Action error: ${err.message}]` },
      ])
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  if (initError) {
    return (
      <div className={styles.errorPage}>
        <p>{initError}</p>
        <Link to="/">← Back to landing</Link>
      </div>
    )
  }

  const health = dashboard?.health || {}
  const phaseCounts = dashboard?.phaseCounts || {}
  const currentPhase = dashboard?.currentTaskPhase

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Link to="/" className={styles.backLink}>← NovaByte</Link>
          <span className={styles.separator} />
          <div className={styles.nameBlock}>
            <span className={styles.name}>{dashboard?.employeeName || 'Loading…'}</span>
            {dashboard?.personaTitle && (
              <span className={styles.persona}>{dashboard.personaTitle}</span>
            )}
          </div>
        </div>

        <div className={styles.phaseBarWrap}>
          <PhaseBar phaseCounts={phaseCounts} currentPhase={currentPhase} />
        </div>

        <div className={styles.headerRight}>
          <div className={styles.integrations}>
            <IntegrationBadge name="Slack" status={health.slack} />
            <IntegrationBadge name="GitHub" status={health.github} />
            <IntegrationBadge name="Jira" status={health.jira} />
          </div>
          <button className={styles.checklistBtn} onClick={() => setShowChecklist(true)}>
            Full checklist
          </button>
          <Link to="/admin" className={styles.adminLink}>Admin view</Link>
        </div>
      </header>

      <div className={styles.body}>
        <div className={styles.chatPane}>
          <div className={styles.chatHeader}>
            <span className={styles.chatTitle}>Session chat</span>
            {loading ? (
              <span className={styles.thinking}>
                <span className={styles.thinkingDots}>
                  <span /><span /><span />
                </span>
                Thinking
              </span>
            ) : (
              <span className={styles.chatMeta}>{messages.length} messages</span>
            )}
          </div>
          <ChatFeed messages={messages} />
          <ChatInput onSend={sendMessage} disabled={loading} />
        </div>

        <div className={styles.taskPane}>
          <TaskPanel dashboard={dashboard} onAction={sendAction} loading={loading} onSendMessage={sendMessage} />
        </div>
      </div>

      {showChecklist && (
        <ChecklistModal sessionId={sessionId} onClose={() => setShowChecklist(false)} />
      )}
    </div>
  )
}
