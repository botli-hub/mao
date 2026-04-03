import React from 'react'
import { Plus, Trash2, Bell, Square } from 'lucide-react'
import { useChatStore } from '../../stores'
import { Button } from '../ui/Button'
import type { Session, ManagedTask } from '../../types'
import { cn } from '../../utils/cn'

interface SessionSidebarProps {
  sessions: Session[]
  managedTasks: ManagedTask[]
  hasOfflineInbox: boolean
  onInboxClick: () => void
  onTerminateTask: (taskId: string) => void
  onCreateSession: () => void
  onDeleteSession: (sessionId: string) => void
}

export function SessionSidebar({
  sessions,
  managedTasks,
  hasOfflineInbox,
  onInboxClick,
  onTerminateTask,
  onCreateSession,
  onDeleteSession,
}: SessionSidebarProps) {
  const { currentSessionId, setCurrentSession } = useChatStore()

  return (
    <div className="w-80 bg-gray-50 border-r border-gray-200 flex flex-col h-full">
      <div className="p-4 border-b border-gray-200 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">会话</h2>
          <button onClick={onInboxClick} className="relative p-1 hover:bg-gray-200 rounded">
            <Bell className="w-5 h-5 text-gray-500" />
            {hasOfflineInbox && (
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-red-500" />
            )}
          </button>
        </div>
        <Button onClick={onCreateSession} size="sm" className="w-full">
          <Plus className="w-4 h-4 mr-2" />
          新建会话
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto border-b border-gray-200">
        {sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">暂无会话</div>
        ) : (
          <div className="space-y-1 p-2">
            {sessions.map((session) => (
              <div
                key={session.session_id}
                className={cn(
                  'group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors',
                  currentSessionId === session.session_id
                    ? 'bg-blue-100 text-blue-900'
                    : 'text-gray-700 hover:bg-gray-200',
                )}
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

      <div className="p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">我的后台托管任务</h3>
        {managedTasks.length === 0 ? (
          <p className="text-xs text-gray-500">暂无托管任务</p>
        ) : (
          <div className="space-y-2 max-h-56 overflow-y-auto">
            {managedTasks.map((task) => (
              <div key={task.task_id} className="bg-white border border-gray-200 rounded-lg p-2.5">
                <p className="text-sm font-medium text-gray-900 truncate">{task.title}</p>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs text-gray-500">{task.task_id}</span>
                  <span
                    className={cn(
                      'text-xs px-2 py-0.5 rounded-full',
                      task.status === 'RUNNING' && 'bg-green-100 text-green-700',
                      task.status === 'SUSPENDED' && 'bg-amber-100 text-amber-700',
                      task.status === 'FAILED' && 'bg-red-100 text-red-700',
                      !['RUNNING', 'SUSPENDED', 'FAILED'].includes(task.status) &&
                        'bg-gray-100 text-gray-700',
                    )}
                  >
                    {task.status}
                  </span>
                </div>
                {(task.status === 'RUNNING' || task.status === 'SUSPENDED') && (
                  <button
                    className="mt-2 w-full text-xs text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded py-1 flex items-center justify-center"
                    onClick={() => onTerminateTask(task.task_id)}
                  >
                    <Square className="w-3 h-3 mr-1" />强制终止
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
