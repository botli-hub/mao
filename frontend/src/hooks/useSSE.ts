import { useEffect, useRef, useCallback } from 'react'
import { createSSE } from '../api/client'
import type { SSEEvent } from '../types'

export function useSSE(sessionId: string, onEvent: (event: SSEEvent) => void) {
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!sessionId) return

    try {
      eventSourceRef.current = createSSE(sessionId)

      eventSourceRef.current.addEventListener('stream_chunk', (e: Event) => {
        const customEvent = e as MessageEvent
        onEvent(JSON.parse(customEvent.data))
      })

      eventSourceRef.current.addEventListener('action_card', (e: Event) => {
        const customEvent = e as MessageEvent
        onEvent(JSON.parse(customEvent.data))
      })

      eventSourceRef.current.addEventListener('task_summary', (e: Event) => {
        const customEvent = e as MessageEvent
        onEvent(JSON.parse(customEvent.data))
      })

      eventSourceRef.current.addEventListener('error', () => {
        eventSourceRef.current?.close()
      })
    } catch (err) {
      console.error('SSE connection error:', err)
    }

    return () => {
      eventSourceRef.current?.close()
    }
  }, [sessionId, onEvent])

  const close = useCallback(() => {
    eventSourceRef.current?.close()
  }, [])

  return { close }
}
