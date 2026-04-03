import React, { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '../../stores'
import { useSSE } from '../../hooks/useSSE'
import { GUICard } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { chatAPI } from '../../api/services'
import type { Message, SSEEvent } from '../../types'
import { cn } from '../../utils/cn'
import toast from 'react-hot-toast'

export function ChatWindow() {
  const {
    currentSessionId,
    messages,
    transientStream,
    addMessage,
    setIsLoading,
    appendTransientStream,
    clearTransientStream,
  } = useChatStore()
  const [inputValue, setInputValue] = React.useState('')
  const [isStreaming, setIsStreaming] = React.useState(false)
  const [lockedCards, setLockedCards] = React.useState<Record<string, boolean>>({})
  const [cardLoading, setCardLoading] = React.useState<Record<string, boolean>>({})
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, transientStream])

  useEffect(() => {
    setIsStreaming(false)
    clearTransientStream()
  }, [currentSessionId, clearTransientStream])

  const handleSSEEvent = (event: SSEEvent) => {
    if (!currentSessionId) return

    if (event.event === 'stream_chunk' && event.data.delta) {
      appendTransientStream(event.data.delta)
      setIsStreaming(true)
      return
    }

    if (event.event === 'action_card' && event.data.card_schema) {
      const msg: Message = {
        message_id: event.data.message_id ?? `msg_${Date.now()}`,
        session_id: currentSessionId,
        role: 'assistant',
        message_type: 'CARD',
        content: '',
        card_schema: event.data.card_schema,
        task_id: event.data.task_id,
        created_at: new Date().toISOString(),
      }
      addMessage(msg)
      clearTransientStream()
      setIsStreaming(false)
      setIsLoading(false)
      return
    }

    if (event.event === 'task_summary') {
      const msg: Message = {
        message_id: event.data.message_id ?? `msg_${Date.now()}`,
        session_id: currentSessionId,
        role: 'assistant',
        message_type: 'TASK_SUMMARY',
        content: event.data.content ?? '',
        quote_ref_id: event.data.quote_ref_id,
        created_at: new Date().toISOString(),
      }
      addMessage(msg)
      setIsStreaming(false)
      clearTransientStream()
      setIsLoading(false)
      return
    }

    if (event.event === 'error') {
      toast.error(event.data.error ?? '任务执行失败')
      setIsStreaming(false)
      clearTransientStream()
      setIsLoading(false)
      return
    }

    if (event.event === 'done') {
      if (transientStream) {
        const msg: Message = {
          message_id: event.data.message_id ?? `msg_${Date.now()}`,
          session_id: currentSessionId,
          role: 'assistant',
          message_type: 'TEXT',
          content: transientStream,
          created_at: new Date().toISOString(),
        }
        addMessage(msg)
      }
      clearTransientStream()
      setIsStreaming(false)
      setIsLoading(false)
    }
  }

  useSSE(currentSessionId ?? '', handleSSEEvent)

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !currentSessionId) return

    const text = inputValue
    const userMsg: Message = {
      message_id: `msg_${Date.now()}`,
      session_id: currentSessionId,
      role: 'user',
      message_type: 'TEXT',
      content: text,
      created_at: new Date().toISOString(),
    }
    addMessage(userMsg)
    clearTransientStream()
    setInputValue('')
    setIsLoading(true)

    try {
      await chatAPI.sendMessage(currentSessionId, text)
    } catch (err) {
      toast.error('发送消息失败')
      setIsLoading(false)
      console.error(err)
    }
  }

  const handleCardAction = async (
    messageId: string,
    actionId: string,
    formData?: Record<string, unknown>,
  ) => {
    if (!currentSessionId) return

    const message = messages.find((item) => item.message_id === messageId)
    if (!message) return

    setCardLoading((prev) => ({ ...prev, [messageId]: true }))

    try {
      await chatAPI.executeCardAction(currentSessionId, messageId, actionId, formData)
      if (message.card_schema?.client_side_lock) {
        setLockedCards((prev) => ({ ...prev, [messageId]: true }))
      }
      toast.success('已提交卡片操作')
    } catch (err) {
      toast.error('卡片提交失败，请重试')
      console.error(err)
    } finally {
      setCardLoading((prev) => ({ ...prev, [messageId]: false }))
    }
  }

  if (!currentSessionId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        选择或创建一个会话开始对话
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-white flex-1">
      <div className="border-b border-gray-200 px-6 py-3 bg-white text-sm text-gray-600">
        💡 为保证响应速度与调度性能，过往长时记忆可能被自动归档。
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.message_id}
            className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
          >
            {msg.message_type === 'CARD' && msg.card_schema ? (
              <div className="max-w-2xl w-full">
                <GUICard
                  schema={msg.card_schema}
                  isLocked={lockedCards[msg.message_id]}
                  isLoading={cardLoading[msg.message_id]}
                  onActionClick={(actionId, formData) => {
                    void handleCardAction(msg.message_id, actionId, formData)
                  }}
                />
              </div>
            ) : (
              <div
                className={cn(
                  'max-w-2xl px-4 py-3 rounded-lg',
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : msg.message_type === 'SYSTEM_NOTICE'
                      ? 'bg-gray-50 text-gray-500 border border-dashed border-gray-300 w-full text-center'
                      : 'bg-gray-100 text-gray-900',
                )}
              >
                {msg.quote_ref_id && (
                  <p className="text-xs text-indigo-600 mb-2">🔗 引用：{msg.quote_ref_id}</p>
                )}
                <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm">
                  {msg.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}
        {isStreaming && transientStream && (
          <div className="flex justify-start">
            <div className="max-w-2xl px-4 py-3 rounded-lg bg-gray-100 text-gray-900">
              <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm">
                {transientStream}
              </ReactMarkdown>
              <span className="animate-pulse">▌</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 p-4 bg-gray-50">
        <div className="flex gap-3">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && void handleSendMessage()}
            placeholder="输入消息..."
            disabled={isStreaming}
          />
          <Button onClick={() => void handleSendMessage()} isLoading={isStreaming}>
            发送
          </Button>
        </div>
      </div>
    </div>
  )
}
