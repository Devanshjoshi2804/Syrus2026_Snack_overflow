import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import styles from './Landing.module.css'

export function Landing() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ employee_name: '', role: '', email: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function handleStart(e) {
    e.preventDefault()
    if (!form.employee_name.trim() || !form.role.trim()) {
      setError('Name and role are required.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const { session_id } = await api.createSession(form)
      navigate(`/onboard/${session_id}`)
    } catch (err) {
      setError(err.message || 'Failed to start session.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.wordmark}>
        <span className={styles.logo}>NB</span>
        <span className={styles.brand}>NovaByte</span>
      </div>

      <div className={styles.split}>
        {/* Left — New Hire */}
        <div className={styles.pane}>
          <div className={styles.paneHeader}>
            <span className={styles.paneTag}>New hire</span>
            <h1 className={styles.paneTitle}>Start your onboarding</h1>
            <p className={styles.paneDesc}>
              The agent will guide you through access setup, environment configuration, and
              team integration — step by step.
            </p>
          </div>

          <form className={styles.form} onSubmit={handleStart}>
            <label className={styles.fieldLabel}>
              Full name
              <input
                className={styles.input}
                type="text"
                value={form.employee_name}
                onChange={(e) => update('employee_name', e.target.value)}
                placeholder="Alex Rivera"
                autoFocus
              />
            </label>

            <label className={styles.fieldLabel}>
              Role / title
              <input
                className={styles.input}
                type="text"
                value={form.role}
                onChange={(e) => update('role', e.target.value)}
                placeholder="Senior Backend Engineer"
              />
            </label>

            <label className={styles.fieldLabel}>
              Work email <span className={styles.optional}>(optional)</span>
              <input
                className={styles.input}
                type="email"
                value={form.email}
                onChange={(e) => update('email', e.target.value)}
                placeholder="alex@novabyte.io"
              />
            </label>

            {error && <p className={styles.error}>{error}</p>}

            <button className={styles.startBtn} type="submit" disabled={loading}>
              {loading ? 'Starting…' : 'Begin onboarding'}
            </button>
          </form>
        </div>

        <div className={styles.divider} />

        {/* Right — Admin */}
        <div className={styles.pane}>
          <div className={styles.paneHeader}>
            <span className={`${styles.paneTag} ${styles.adminTag}`}>Admin</span>
            <h1 className={styles.paneTitle}>Member progress</h1>
            <p className={styles.paneDesc}>
              View all active onboarding sessions, integration status, and task completion
              across the team.
            </p>
          </div>

          <div className={styles.adminActions}>
            <button
              className={styles.adminBtn}
              onClick={() => navigate('/admin')}
            >
              Open admin dashboard →
            </button>
          </div>
        </div>
      </div>

      <footer className={styles.footer}>
        PS-03 · Onboarding Automation Agent · NovaByte Engineering
      </footer>
    </div>
  )
}
