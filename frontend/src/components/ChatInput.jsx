import { useState, useRef } from 'react'
import styles from './ChatInput.module.css'

const QUICK_CHIPS = [
  "Explain this step",
  "Who do I contact?",
  "How long is left?",
  "I'm stuck",
  "Why does this matter?",
]

export function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    textareaRef.current?.focus()
  }

  function sendChip(chip) {
    if (disabled) return
    onSend(chip)
    textareaRef.current?.focus()
  }

  return (
    <div className={styles.container}>
      <div className={styles.chips}>
        {QUICK_CHIPS.map((chip) => (
          <button
            key={chip}
            className={styles.chip}
            onClick={() => sendChip(chip)}
            disabled={disabled}
          >
            {chip}
          </button>
        ))}
      </div>
      <div className={styles.wrap}>
        <textarea
          ref={textareaRef}
          className={styles.input}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything, or type $ <command> to run in terminal…"
          rows={2}
          disabled={disabled}
        />
        <button
          className={styles.btn}
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send"
        >
          Send
        </button>
      </div>
    </div>
  )
}
