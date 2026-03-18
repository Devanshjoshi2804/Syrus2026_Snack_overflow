import styles from './StatusPill.module.css'

const STATUS_CLASS = {
  COMPLETED: 'completed',
  IN_PROGRESS: 'inProgress',
  NOT_STARTED: 'notStarted',
  BLOCKED: 'blocked',
  SKIPPED: 'skipped',
  DEFERRED: 'deferred',
}

export function StatusPill({ status }) {
  const cls = STATUS_CLASS[status] || 'notStarted'
  const label =
    status === 'NOT_STARTED'
      ? 'Not started'
      : status === 'IN_PROGRESS'
        ? 'In progress'
        : status
          ? status.charAt(0) + status.slice(1).toLowerCase()
          : '—'

  return <span className={`${styles.pill} ${styles[cls]}`}>{label}</span>
}
