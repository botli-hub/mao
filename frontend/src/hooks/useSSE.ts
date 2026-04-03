import { useEffect, useRef, useCallback } from 'react'
import { createSSE } from '../api/client'
import type { SSEEvent } from '../types'

export function useSSE(sessionId: string, onEvent: (event: SSEEvent) => void) {
  const eventSourceRef = useRef<EventSource | null>(null)
  const handleRawEvent = useCallback(
    (raw: unknown) => {
      if (!raw || typeof raw !== 'object') return
      const payload = raw as Record<string, unknown>
      if (typeof payload.event !== 'string') return
      const normalized: SSEEvent = {
        event: payload.event as SSEEvent['event'],
        data: (payload.data as SSEEvent['data']) ?? (payload as SSEEvent['data']),
      }
      onEvent(normalized)
    },
    [onEvent],
  )

  const handleMessageEvent = useCallback(
    (e: Event) => {
      const customEvent = e as MessageEvent
      try {
        handleRawEvent(JSON.parse(customEvent.data))
      } catch (err) {
        console.error('Failed to parse SSE event:', err)
      }
    },
    [handleRawEvent],
  )

  useEffect(() => {
    if (!sessionId) return

    try {
      eventSourceRef.current = createSSE(sessionId)

      // 后端默认通过 `data:` 推送 JSON，未显式设置 SSE event 字段，因此统一监听 message
      eventSourceRef.current.addEventListener('message', handleMessageEvent)
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
