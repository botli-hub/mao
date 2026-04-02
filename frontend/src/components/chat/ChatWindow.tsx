import React, { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '../../stores'
import { useSSE } from '../../hooks/useSSE'
import { GUICard } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Message, SSEEvent } from '../../types'
import { cn } from '../../utils/cn'

export function ChatWindow() {
  const { currentSessionId, messages, addMessage, setIsLoading } = useChatStore()
  const [inputValue, setInputValue] = React.useState('')
  const [isStreaming, setIsStreaming] = React.useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const currentMessageRef = useRef<string>('')

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSSEEvent = (event: SSEEvent) => {
    if (event.event === 'stream_chunk' && event.data.delta) {
      currentMessageRef.current += event.data.delta
      setIsStreaming(true)
    } else if (event.event === 'action_card' && event.data.card_schema) {
      const msg: Message = {
        message_id: event.data.message_id ?? `msg_${Date.now()}`,
        session_id: currentSessionId!,
        role: 'assistant',
        message_type: 'CARD',
        content: '',
        card_schema: event.data.card_schema,
        created_at: new Date().toISOString(),
      }
      addMessage(msg)
      currentMessageRef.current = ''
    } else if (event.event === 'task_summary') {
      const msg: Message = {
        message_id: event.data.message_id ?? `msg_${Date.now()}`,
        session_id: currentSessionId!,
        role: 'assistant',
        message_type: 'TASK_SUMMARY',
        content: event.data.content ?? '',
        created_at: new Date().toISOString(),
      }
      addMessage(msg)
      setIsStreaming(false)
      setIsLoading(false)
    } else if (event.event === 'done') {
      if (currentMessageRef.current) {
        const msg: Message = {
          message_id: event.data.message_id ?? `msg_${Date.now()}`,
          session_id: currentSessionId!,
          role: 'assistant',
          message_type: 'TEXT',
          content: currentMessageRef.current,
          created_at: new Date().toISOString(),
        }
        addMessage(msg)
        currentMessageRef.current = ''
      }
      setIsStreaming(false)
      setIsLoading(false)
    }
  }

  useSSE(currentSessionId ?? '', handleSSEEvent)

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !currentSessionId) return

    const userMsg: Message = {
      message_id: `msg_${Date.now()}`,
      session_id: currentSessionId,
      role: 'user',
      message_type: 'TEXT',
      content: inputValue,
      created_at: new Date().toISOString(),
    }
    addMessage(userMsg)
    setInputValue('')
    setIsLoading(true)

    // 实际实现应调用 chatAPI.sendMessage
  }

  if (!currentSessionId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        选择或创建一个会话开始对话
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-white">
      {/* 消息列表 */}
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
                  onActionClick={(actionId, formData) => {
                    // 实际实现应调用 chatAPI.executeCardAction
                    console.log('Action clicked:', actionId, formData)
                  }}
                />
              </div>
            ) : (
              <div
                className={cn(
                  'max-w-2xl px-4 py-3 rounded-lg',
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-900',
                )}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm">
                  {msg.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}
        {isStreaming && currentMessageRef.current && (
          <div className="flex justify-start">
            <div className="max-w-2xl px-4 py-3 rounded-lg bg-gray-100 text-gray-900">
              <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm">
                {currentMessageRef.current}
              </ReactMarkdown>
              <span className="animate-pulse">▌</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入框 */}
      <div className="border-t border-gray-200 p-4 bg-gray-50">
        <div className="flex gap-3">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
            placeholder="输入消息..."
            disabled={isStreaming}
          />
          <Button onClick={handleSendMessage} isLoading={isStreaming}>
            发送
          </Button>
        </div>
      </div>
    </div>
  )
}
