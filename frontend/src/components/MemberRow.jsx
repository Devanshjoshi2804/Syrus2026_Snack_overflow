import { Link } from 'react-router-dom'
import { PhaseBar } from './PhaseBar'
import { IntegrationBadge } from './IntegrationBadge'
import { StatusPill } from './StatusPill'
import styles from './MemberRow.module.css'

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function MemberRow({ member }) {
  const {
    session_id,
    employee_name,
    role,
    created_at,
    completed_tasks,
    total_tasks,
    progress_pct,
    current_task,
    current_phase,
    phase_counts,
    integration_health,
  } = member

  const health = integration_health || {}

  return (
    <tr className={styles.row}>
      <td className={styles.nameCell}>
        <Link to={`/onboard/${session_id}`} className={styles.nameLink}>
          {employee_name || '—'}
        </Link>
        <span className={styles.role}>{role || '—'}</span>
      </td>
      <td className={styles.phaseCell}>
        <PhaseBar phaseCounts={phase_counts} currentPhase={current_phase} />
      </td>
      <td className={styles.progressCell}>
        <span className={styles.pct}>{progress_pct}%</span>
        <span className={styles.fraction}>
          {completed_tasks}/{total_tasks}
        </span>
      </td>
      <td className={styles.taskCell}>
        <span className={styles.taskLabel} title={current_task}>
          {current_task || '—'}
        </span>
      </td>
      <td className={styles.intCell}>
        <div className={styles.badges}>
          <IntegrationBadge name="Slack" status={health.slack} />
          <IntegrationBadge name="GitHub" status={health.github} />
          <IntegrationBadge name="Jira" status={health.jira} />
        </div>
      </td>
      <td className={styles.dateCell}>{fmtDate(created_at)}</td>
    </tr>
  )
}
