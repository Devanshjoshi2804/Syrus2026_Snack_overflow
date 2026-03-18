const BASE = '/api'

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${method} ${path} → ${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  health: () => request('GET', '/health'),

  // Admin
  listMembers: () => request('GET', '/admin/members'),

  // Sessions
  createSession: (body) => request('POST', '/sessions', body),
  getSession: (id) => request('GET', `/sessions/${id}`),
  sendMessage: (id, content) => request('POST', `/sessions/${id}/message`, { content }),
  sendAction: (id, action, task_id) =>
    request('POST', `/sessions/${id}/action`, { action, task_id }),
  getChecklist: (id) => request('GET', `/sessions/${id}/checklist`),
  runTerminal: (id, command) => request('POST', `/sessions/${id}/terminal`, { command }),
}

/**
 * WebSocket hook helper (plain JS class — use inside React with useEffect).
 *
 * Usage:
 *   const ws = new SessionSocket(sessionId, onMessage)
 *   ws.connect()
 *   // cleanup:
 *   ws.close()
 */
export class SessionSocket {
  constructor(sessionId, onMessage) {
    this.sessionId = sessionId
    this.onMessage = onMessage
    this._ws = null
    this._ping = null
  }

  connect() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/${this.sessionId}`
    this._ws = new WebSocket(url)

    this._ws.onmessage = (evt) => {
      try {
        this.onMessage(JSON.parse(evt.data))
      } catch (_) {
        // ignore non-JSON (e.g. "pong")
      }
    }

    this._ws.onopen = () => {
      this._ping = setInterval(() => {
        if (this._ws?.readyState === WebSocket.OPEN) {
          this._ws.send('ping')
        }
      }, 20_000)
    }

    this._ws.onclose = () => {
      clearInterval(this._ping)
    }
  }

  close() {
    clearInterval(this._ping)
    this._ws?.close()
  }
}
