import { useCallback, useState } from 'react'
import { streamQuery } from '../lib/streamQuery'

let nextMessageId = 1

export function useChat() {
  const [messages, setMessages] = useState([])
  const [activeTrace, setActiveTrace] = useState([])
  const [isTraceOpen, setIsTraceOpen] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState(null)

  const submitQuestion = useCallback(
    async (question) => {
      const trimmed = question.trim()
      if (!trimmed || isStreaming) return

      setError(null)
      setActiveTrace([])
      setIsTraceOpen(true)
      setIsStreaming(true)

      // Accumulated locally (not just via setState) so the "done" handler
      // can attach the full trace to the finished message without racing
      // React's async state updates.
      const trace = []

      await streamQuery(trimmed, {
        onNodeUpdate: (event) => {
          trace.push(event)
          setActiveTrace([...trace])
        },
        onDone: (payload) => {
          setMessages((prev) => [
            ...prev,
            {
              id: nextMessageId++,
              question: trimmed,
              trace: [...trace],
              ...payload,
            },
          ])
          setIsStreaming(false)
          setIsTraceOpen(false)
        },
        onError: (err) => {
          setError(err.message ?? 'Something went wrong talking to the agent.')
          setIsStreaming(false)
        },
      })
    },
    [isStreaming],
  )

  return {
    messages,
    activeTrace,
    isTraceOpen,
    setIsTraceOpen,
    isStreaming,
    error,
    submitQuestion,
  }
}
