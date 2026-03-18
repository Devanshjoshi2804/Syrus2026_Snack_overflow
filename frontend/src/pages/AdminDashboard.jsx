import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { MemberRow } from '../components/MemberRow'
import styles from './AdminDashboard.module.css'

function fmtTs(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

export function AdminDashboard() {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastRefresh, setLastRefresh] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const data = await api.listMembers()
      setMembers(data)
      setLastRefresh(new Date().toISOString())
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 15_000)
    return () => clearInterval(timer)
  }, [refresh])

  const totalComplete = members.reduce((sum, m) => sum + (m.completed_tasks || 0), 0)
  const totalTasks = members.reduce((sum, m) => sum + (m.total_tasks || 0), 0)

  return (
    <div className={styles.page}>
      {/* Top bar */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Link to="/" className={styles.backLink}>← NovaByte</Link>
          <h1 className={styles.title}>Onboarding Dashboard</h1>
        </div>
        <div className={styles.headerRight}>
          {lastRefresh && (
            <span className={styles.refreshed}>
              Refreshed {fmtTs(lastRefresh)}
            </span>
          )}
          <button className={styles.refreshBtn} onClick={refresh} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
          <Link to="/" className={styles.newBtn}>+ New hire</Link>
        </div>
      </header>

      {/* Summary row */}
      {members.length > 0 && (
        <div className={styles.summary}>
          <div className={styles.stat}>
            <span className={styles.statVal}>{members.length}</span>
            <span className={styles.statLabel}>Active sessions</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.stat}>
            <span className={styles.statVal}>{totalComplete}</span>
            <span className={styles.statLabel}>Tasks completed</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.stat}>
            <span className={styles.statVal}>
              {totalTasks > 0 ? Math.round((totalComplete / totalTasks) * 100) : 0}%
            </span>
            <span className={styles.statLabel}>Overall progress</span>
          </div>
        </div>
      )}

      {/* Main table */}
      <div className={styles.tableWrap}>
        {error && <div className={styles.error}>{error}</div>}

        {!loading && members.length === 0 && !error && (
          <div className={styles.empty}>
            <p>No active sessions. Start by adding a new hire on the landing page.</p>
            <Link to="/" className={styles.emptyLink}>Go to landing page →</Link>
          </div>
        )}

        {members.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Member</th>
                <th>Phase progress</th>
                <th>Done</th>
                <th>Current task</th>
                <th>Integrations</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <MemberRow key={m.session_id} member={m} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
