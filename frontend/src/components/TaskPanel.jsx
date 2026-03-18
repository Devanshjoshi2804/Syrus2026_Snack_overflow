import { useState } from 'react'
import { StatusPill } from './StatusPill'
import styles from './TaskPanel.module.css'

const ACTION_CLASS = {
  watch_agent: 'primary',
  self_complete: 'secondary',
  skip: 'ghost',
}

function TerminalPane({ transcript, artifacts }) {
  const lines = transcript
    ? transcript.split('\n')
    : ['No terminal output yet.', 'Run the agent to see execution logs here.']

  return (
    <div className={styles.terminal}>
      <div className={styles.terminalBar}>
        <span className={styles.termDot} style={{ background: '#FF5F57' }} />
        <span className={styles.termDot} style={{ background: '#FEBC2E' }} />
        <span className={styles.termDot} style={{ background: '#28C840' }} />
        <span className={styles.termLabel}>agent output</span>
      </div>
      <pre className={styles.termBody}>
        {lines.map((line, i) => {
          const isCmd = line.startsWith('$') || line.startsWith('>')
          const isErr = /error|fail|exit code/i.test(line)
          const isOk = /success|✓|done|completed/i.test(line)
          const cls = isCmd ? styles.termCmd : isErr ? styles.termErr : isOk ? styles.termOk : ''
          return (
            <span key={i} className={`${styles.termLine} ${cls}`}>
              {line}
              {'\n'}
            </span>
          )
        })}
        <span className={styles.termCursor}>█</span>
      </pre>
      {artifacts && artifacts.length > 0 && (
        <div className={styles.artifacts}>
          {artifacts.map((a, i) => (
            <span key={i} className={styles.artifact}>{a.split('/').pop()}</span>
          ))}
        </div>
      )}
    </div>
  )
}

export function TaskPanel({ dashboard, onAction, loading, onSendMessage }) {
  const [tab, setTab] = useState('task') // 'task' | 'terminal'

  if (!dashboard) {
    return <div className={styles.empty}><p>No session loaded.</p></div>
  }

  const {
    currentTaskId,
    currentTask,
    currentTaskPhase,
    currentTaskCategory,
    currentTaskAutomation,
    currentTaskStatus,
    currentTaskEvidence,
    currentTaskPriority,
    availableActions,
    actionLabels,
    completedTasks,
    totalTasks,
    guidedStep,
    latestStatus,
    latestTranscript,
    latestArtifacts,
    nextAgentTask,
  } = dashboard

  const pct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0
  const steps = guidedStep?.what_to_do_now || []
  const actions = availableActions || []
  const labels = actionLabels || {}
  const hasTerminal = !!latestTranscript
  const timeEstimate = guidedStep?.time_estimate || null
  const escalationContact = guidedStep?.escalation_contact || null
  const blockedHint = guidedStep?.blocked_hint || null
  const isRequired = currentTaskPriority === 'required'
  const isBlocked = currentTaskStatus === 'blocked'

  return (
    <div className={styles.panel}>
      {/* Progress strip */}
      <div className={styles.progressStrip}>
        <div className={styles.progressMeta}>
          <span className={styles.progressPct}>{pct}%</span>
          <span className={styles.progressFraction}>{completedTasks} of {totalTasks} tasks</span>
        </div>
        <div className={styles.progressTrack}>
          <div className={styles.progressFill} style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Tab bar */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${tab === 'task' ? styles.tabActive : ''}`}
          onClick={() => setTab('task')}
        >
          Task
        </button>
        <button
          className={`${styles.tab} ${tab === 'terminal' ? styles.tabActive : ''}`}
          onClick={() => setTab('terminal')}
        >
          Terminal
          {hasTerminal && tab !== 'terminal' && <span className={styles.termBadge} />}
        </button>
      </div>

      {tab === 'terminal' ? (
        <TerminalPane transcript={latestTranscript} artifacts={latestArtifacts} />
      ) : (
        <>
          {/* Task header */}
          <div className={styles.taskCard}>
            <div className={styles.taskMeta}>
              {currentTaskId && (
                <span className={styles.taskId}>{currentTaskId}</span>
              )}
              {isRequired && (
                <span className={styles.requiredBadge}>Required</span>
              )}
              {currentTaskAutomation && (
                <span className={styles.autoTag}>
                  {currentTaskAutomation.replace(/_/g, ' ')}
                </span>
              )}
              {timeEstimate && (
                <span className={styles.timeEstimate}>⏱ {timeEstimate}</span>
              )}
              <StatusPill status={currentTaskStatus} />
            </div>

            {currentTaskPhase && (
              <div className={styles.phase}>{currentTaskPhase.replace(/_/g, ' ')}</div>
            )}

            <h2 className={styles.taskTitle}>{currentTask || 'No active task'}</h2>

            {currentTaskCategory && (
              <div className={styles.category}>{currentTaskCategory}</div>
            )}

            {isBlocked && blockedHint && (
              <div className={styles.blockedHint}>
                <span className={styles.blockedIcon}>⚠</span>
                {blockedHint}
              </div>
            )}

            {currentTaskEvidence && currentTaskEvidence.length > 0 && (
              <div className={styles.evidence}>
                <div className={styles.evidenceLabel}>Evidence required</div>
                <ul className={styles.evidenceList}>
                  {currentTaskEvidence.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Steps */}
          {steps.length > 0 && (
            <div className={styles.steps}>
              <div className={styles.sectionLabel}>Steps</div>
              <ol className={styles.stepList}>
                {steps.map((step, i) => (
                  <li key={i} className={styles.step}>{step}</li>
                ))}
              </ol>
            </div>
          )}

          {/* Latest status */}
          {latestStatus && (
            <div className={styles.statusBar}>
              <span className={styles.statusDot} />
              <span className={styles.statusText}>{latestStatus}</span>
            </div>
          )}

          {/* Actions */}
          {actions.length > 0 && (
            <div className={styles.actions}>
              {actions.map((action) => {
                const cls = ACTION_CLASS[action] || 'ghost'
                const label = labels[action] || action.replace(/_/g, ' ')
                return (
                  <button
                    key={action}
                    className={`${styles.actionBtn} ${styles[cls]}`}
                    onClick={() => onAction(action)}
                    disabled={loading}
                  >
                    {loading && action === 'watch_agent' ? (
                      <><span className={styles.spinner} /> Running…</>
                    ) : label}
                  </button>
                )
              })}
            </div>
          )}

          {/* Stuck / escalation */}
          {escalationContact && (
            <div className={styles.escalation}>
              <div className={styles.escalationLabel}>Need help?</div>
              <div className={styles.escalationContact}>{escalationContact}</div>
              {blockedHint && !isBlocked && (
                <div className={styles.escalationHint}>{blockedHint}</div>
              )}
              {onSendMessage && (
                <button
                  className={styles.stuckBtn}
                  onClick={() => onSendMessage("I'm stuck on this step — who do I contact?")}
                  disabled={loading}
                >
                  I'm stuck — get help
                </button>
              )}
            </div>
          )}

          {/* Next hint */}
          {nextAgentTask && (
            <div className={styles.nextHint}>
              <span className={styles.nextLabel}>Up next</span>
              <span className={styles.nextTask}>
                {typeof nextAgentTask === 'object'
                  ? `${nextAgentTask.taskId} — ${nextAgentTask.title}`
                  : nextAgentTask}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
