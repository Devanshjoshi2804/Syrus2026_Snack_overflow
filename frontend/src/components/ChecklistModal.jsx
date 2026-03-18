import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { StatusPill } from './StatusPill'
import styles from './ChecklistModal.module.css'

const PHASE_ORDER = ['GET_ACCESS', 'GET_CODING', 'LEARN_SYSTEM', 'ADMIN_COMPLIANCE']

function groupByPhase(tasks) {
  const groups = {}
  for (const t of tasks) {
    const phase = t.phase || 'OTHER'
    if (!groups[phase]) groups[phase] = []
    groups[phase].push(t)
  }
  return groups
}

export function ChecklistModal({ sessionId, onClose }) {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getChecklist(sessionId)
      .then((data) => setTasks(data.tasks || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionId])

  const groups = groupByPhase(tasks)

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>Full Task Checklist</h2>
          <button className={styles.close} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {loading ? (
          <div className={styles.loading}>Loading…</div>
        ) : (
          <div className={styles.body}>
            {PHASE_ORDER.map((phase) => {
              const phaseTasks = groups[phase]
              if (!phaseTasks) return null
              return (
                <div key={phase} className={styles.group}>
                  <div className={styles.groupHeader}>{phase.replace(/_/g, ' ')}</div>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Task</th>
                        <th>Automation</th>
                        <th>Priority</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {phaseTasks.map((t) => (
                        <tr key={t.task_id} className={styles.taskRow}>
                          <td className={styles.id}>
                            <code>{t.task_id}</code>
                          </td>
                          <td className={styles.taskTitle}>{t.title}</td>
                          <td className={styles.mode}>
                            {t.automation_mode?.replace(/_/g, ' ') || '—'}
                          </td>
                          <td className={styles.priority}>{t.priority || '—'}</td>
                          <td>
                            <StatusPill status={t.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
