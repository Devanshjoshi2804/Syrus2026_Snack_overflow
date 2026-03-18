import { useEffect, useRef } from 'react'
import styles from './ChatFeed.module.css'

// ── Markdown-lite renderer ──────────────────────────────────────────────────

function renderMarkdown(text) {
  const nodes = []
  const lines = text.split('\n')
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Numbered list item
    if (/^\d+\.\s/.test(line)) {
      const items = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ''))
        i++
      }
      nodes.push(
        <ol key={nodes.length} className={styles.ol}>
          {items.map((item, j) => (
            <li key={j}>{renderInline(item)}</li>
          ))}
        </ol>
      )
      continue
    }

    // Bullet list
    if (/^[-*]\s/.test(line)) {
      const items = []
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, ''))
        i++
      }
      nodes.push(
        <ul key={nodes.length} className={styles.ul}>
          {items.map((item, j) => (
            <li key={j}>{renderInline(item)}</li>
          ))}
        </ul>
      )
      continue
    }

    // Fenced code block
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim()
      const codeLines = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      i++ // skip closing ```
      nodes.push(
        <pre key={nodes.length} className={styles.codeBlock}>
          {lang && <span className={styles.codeLang}>{lang}</span>}
          <code>{codeLines.join('\n')}</code>
        </pre>
      )
      continue
    }

    // Empty line → paragraph break
    if (line.trim() === '') {
      nodes.push(<div key={nodes.length} className={styles.spacer} />)
      i++
      continue
    }

    // Normal paragraph line
    nodes.push(
      <p key={nodes.length} className={styles.para}>
        {renderInline(line)}
      </p>
    )
    i++
  }

  return nodes
}

function renderInline(text) {
  // Split by inline patterns: **bold**, *italic*, `code`, URLs
  const parts = []
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|https?:\/\/\S+)/g
  let last = 0
  let m

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) {
      parts.push(<strong key={m.index}>{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('*')) {
      parts.push(<em key={m.index}>{tok.slice(1, -1)}</em>)
    } else if (tok.startsWith('`')) {
      parts.push(<code key={m.index} className={styles.inlineCode}>{tok.slice(1, -1)}</code>)
    } else if (tok.startsWith('http')) {
      const display = tok.length > 60 ? tok.slice(0, 57) + '…' : tok
      parts.push(
        <a key={m.index} href={tok} target="_blank" rel="noopener noreferrer" className={styles.link}>
          {display}
        </a>
      )
    }
    last = m.index + tok.length
  }

  if (last < text.length) parts.push(text.slice(last))
  return parts.length ? parts : text
}

// ── Terminal helpers ────────────────────────────────────────────────────────

// Collapse ####...x% download progress into a single summary line
function cleanTerminalLines(raw) {
  const lines = raw.split('\n')
  const out = []
  let inProgress = false
  let lastPct = null

  for (const line of lines) {
    const pctMatch = line.match(/^\s*#+\s+([\d.]+)%/)
    const curlProgress = line.match(/^\s*\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+--:--:--/)
    const curlHeader = /^\s*% Total\s+% Received\s+% Xferd/.test(line) || /^\s*Dload\s+Upload\s+Total\s+Spent/.test(line)
    if (pctMatch) {
      inProgress = true
      lastPct = pctMatch[1]
      continue
    }
    if (curlHeader || curlProgress) {
      continue
    }
    if (inProgress) {
      out.push(`  [download] ${lastPct}% complete`)
      inProgress = false
      lastPct = null
    }
    if (line.trim() === '' && out[out.length - 1] === '') {
      continue
    }
    out.push(line)
  }
  if (inProgress) out.push(`  [download] ${lastPct}% complete`)
  return out.join('\n')
}

function classifyLine(line) {
  if (/^[\$>]\s/.test(line.trim())) return styles.termCmd
  if (/\b(error|fail|exit code \d+|not compatible|unset)/i.test(line)) return styles.termErr
  if (/\b(success|done|completed|✓|installed|passed|matched|already installed|default alias)/i.test(line)) return styles.termOk
  if (/^==>|^=>/.test(line.trim())) return styles.termMuted
  if (/\[download\]/.test(line)) return styles.termMuted
  return styles.termNormal
}

// ── Components ──────────────────────────────────────────────────────────────

function isAction(content) {
  return /^\[action:/i.test(content)
}

function actionLabel(content) {
  const m = content.match(/\[action:\s*(\w+)\]/)
  if (!m) return content.replace(/^\[|\]$/g, '')
  const map = { watch_agent: 'Run agent', self_complete: 'Mark done', skip: 'Skip task' }
  return map[m[1]] || m[1].replace(/_/g, ' ')
}

const ACTION_ICON = { watch_agent: '▶', self_complete: '✓', skip: '→' }
function getActionIcon(content) {
  const m = content.match(/\[action:\s*(\w+)\]/)
  return m ? (ACTION_ICON[m[1]] || '⚡') : '⚡'
}

function TerminalBlock({ content, taskId, success }) {
  const cleaned = cleanTerminalLines(content || 'No output captured.')
  const lines = cleaned.split('\n')
  const failed = success === false

  return (
    <div className={`${styles.termBlock} ${failed ? styles.termBlockFailed : ''}`}>
      <div className={styles.termBlockBar}>
        <span className={styles.termDot} style={{ background: '#FF5F57' }} />
        <span className={styles.termDot} style={{ background: '#FEBC2E' }} />
        <span className={styles.termDot} style={{ background: failed ? '#444' : '#28C840' }} />
        <span className={styles.termBlockLabel}>
          agent run{taskId ? ` · ${taskId}` : ''}
        </span>
        {failed && <span className={styles.termFailedBadge}>blocked</span>}
        {!failed && success === true && <span className={styles.termOkBadge}>success</span>}
      </div>
      <pre className={styles.termBlockBody}>
        {lines.map((line, i) => (
          <span key={i} className={classifyLine(line)}>{line}{'\n'}</span>
        ))}
        <span className={styles.termCursor}>█</span>
      </pre>
    </div>
  )
}

function MessageBubble({ msg }) {
  if (isAction(msg.content)) {
    return (
      <div className={styles.actionEvent}>
        <span className={styles.actionIcon}>{getActionIcon(msg.content)}</span>
        <span className={styles.actionText}>{actionLabel(msg.content)}</span>
      </div>
    )
  }

  if (msg.role === 'terminal') {
    return <TerminalBlock content={msg.content} taskId={msg.taskId} success={msg.success} />
  }

  const isAgent = msg.role === 'assistant'
  return (
    <div className={`${styles.bubble} ${isAgent ? styles.agent : styles.user}`}>
      <div className={styles.meta}>{isAgent ? 'OnboardAI' : 'You'}</div>
      <div className={styles.body}>
        {isAgent ? renderMarkdown(msg.content) : <span className={styles.text}>{msg.content}</span>}
      </div>
    </div>
  )
}

// ── Feed ────────────────────────────────────────────────────────────────────

export function ChatFeed({ messages = [] }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  if (messages.length === 0) {
    return (
      <div className={styles.empty}>
        <p>Send a message to begin your session.</p>
      </div>
    )
  }

  return (
    <div className={styles.feed}>
      {messages.map((msg, i) => (
        <MessageBubble key={i} msg={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
