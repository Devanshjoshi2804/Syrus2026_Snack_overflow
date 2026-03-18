import styles from './IntegrationBadge.module.css'

const STATUS_ICON = {
  ok: '✓',
  connected: '✓',
  healthy: '✓',
  unknown: '?',
  pending: '…',
  error: '✕',
  failed: '✕',
  disabled: '—',
  mock: '~',
}

function dot(status = 'unknown') {
  const s = String(status).toLowerCase()
  if (s === 'ok' || s === 'connected' || s === 'healthy') return 'ok'
  if (s === 'pending' || s === 'unknown') return 'pending'
  if (s === 'mock') return 'mock'
  return 'error'
}

export function IntegrationBadge({ name, status }) {
  const state = dot(status)
  const icon = STATUS_ICON[String(status).toLowerCase()] ?? '?'

  return (
    <span className={`${styles.badge} ${styles[state]}`} title={`${name}: ${status}`}>
      <span className={styles.dot} />
      {name}
      <span className={styles.icon}>{icon}</span>
    </span>
  )
}
