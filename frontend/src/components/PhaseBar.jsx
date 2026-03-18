import styles from './PhaseBar.module.css'

const PHASES = [
  { key: 'get_access', label: 'GET ACCESS' },
  { key: 'get_coding', label: 'GET CODING' },
  { key: 'learn_system', label: 'LEARN SYSTEM' },
  { key: 'admin_compliance', label: 'ADMIN' },
]

export function PhaseBar({ phaseCounts = {}, currentPhase }) {
  return (
    <div className={styles.bar}>
      {PHASES.map(({ key, label }) => {
        const counts = phaseCounts[key] || {}
        const total = counts.total || 0
        const done = counts.resolved || 0
        const pct = total > 0 ? Math.round((done / total) * 100) : 0
        const isActive = currentPhase === key
        const isDone = total > 0 && pct === 100

        return (
          <div
            key={key}
            className={`${styles.segment} ${isActive ? styles.active : ''} ${isDone ? styles.done : ''}`}
          >
            <div className={styles.fill} style={{ width: `${pct}%` }} />
            <span className={styles.label}>{label}</span>
            <span className={styles.count}>
              {total > 0 ? `${done}/${total}` : '—'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
