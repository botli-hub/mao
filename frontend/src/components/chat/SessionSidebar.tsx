import React from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useChatStore } from '../../stores'
import { Button } from '../ui/Button'
import type { Session } from '../../types'

interface SessionSidebarProps {
  sessions: Session[]
  onCreateSession: () => void
  onDeleteSession: (sessionId: string) => void
}

export function SessionSidebar({ sessions, onCreateSession, onDeleteSession }: SessionSidebarProps) {
  const { currentSessionId, setCurrentSession } = useChatStore()

  return (
    <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col h-full">
      {/* 标题 */}
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">会话</h2>
        <Button onClick={onCreateSession} size="sm" className="w-full">
          <Plus className="w-4 h-4 mr-2" />
          新建会话
        </Button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">暂无会话</div>
        ) : (
          <div className="space-y-1 p-2">
            {sessions.map((session) => (
              <div
                key={session.session_id}
                className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
                  currentSessionId === session.session_id
                    ? 'bg-blue-100 text-blue-900'
                    : 'text-gray-700 hover:bg-gray-200'
                }`}
                onClick={() => setCurrentSession(session.session_id)}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{session.title}</p>
                  {session.last_message && (
                    <p className="text-xs text-gray-500 truncate">{session.last_message}</p>
                  )}
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onDeleteSession(session.session_id)
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 rounded transition-opacity"
                >
                  <Trash2 className="w-4 h-4 text-red-600" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
