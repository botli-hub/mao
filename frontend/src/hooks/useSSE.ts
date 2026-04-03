import { useEffect, useRef, useCallback } from 'react'
import { createSSE } from '../api/client'
import type { SSEEvent } from '../types'

export function useSSE(sessionId: string, onEvent: (event: SSEEvent) => void) {
  const eventSourceRef = useRef<EventSource | null>(null)
  const handleMessageEvent = useCallback(
    (e: Event) => {
      const customEvent = e as MessageEvent
      try {
        onEvent(JSON.parse(customEvent.data))
      } catch (err) {
        console.error('Failed to parse SSE event:', err)
      }
    },
    [onEvent],
  )

  useEffect(() => {
    if (!sessionId) return

    try {
      eventSourceRef.current = createSSE(sessionId)

      eventSourceRef.current.addEventListener('stream_chunk', handleMessageEvent)
      eventSourceRef.current.addEventListener('action_card', handleMessageEvent)
      eventSourceRef.current.addEventListener('task_summary', handleMessageEvent)
      eventSourceRef.current.addEventListener('done', handleMessageEvent)
      eventSourceRef.current.addEventListener('task_status', handleMessageEvent)
      eventSourceRef.current.addEventListener('error', handleMessageEvent)
    } catch (err) {
      console.error('SSE connection error:', err)
    }

    return () => {
      eventSourceRef.current?.close()
    }
  }, [sessionId, handleMessageEvent])

  const close = useCallback(() => {
    eventSourceRef.current?.close()
  }, [])

  return { close }
}
