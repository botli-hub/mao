import React, { useEffect } from 'react'
import { useChatStore } from '../../stores'
import { auditAPI, chatAPI } from '../../api/services'
import { ChatWindow } from '../../components/chat/ChatWindow'
import { SessionSidebar } from '../../components/chat/SessionSidebar'
import type { ManagedTask } from '../../types'
import toast from 'react-hot-toast'

export function ChatPage() {
  const { sessions, currentSessionId, setSessions, setMessages } = useChatStore()
  const [managedTasks, setManagedTasks] = React.useState<ManagedTask[]>([])
  const [hasOfflineInbox, setHasOfflineInbox] = React.useState(false)

  useEffect(() => {
    void loadSessions()
    void loadManagedTasks()
  }, [])

  useEffect(() => {
    if (!currentSessionId) return
    void loadSessionMessages(currentSessionId)
  }, [currentSessionId])

  const loadSessions = async () => {
    try {
      const res = await chatAPI.getSessions()
      const data = res.data.items
      setSessions(data)
      if (data.length > 0 && !currentSessionId) {
        useChatStore.getState().setCurrentSession(data[0].session_id)
      }
    } catch (err) {
      toast.error('加载会话失败')
      console.error(err)
    }
  }

  const loadManagedTasks = async () => {
    try {
      const res = await chatAPI.getManagedTasks()
      setManagedTasks(res.data.items)
    } catch (err) {
      console.error('加载托管任务失败', err)
    }
  }

  const loadSessionMessages = async (sessionId: string) => {
    try {
      const inboxRes = await chatAPI.getOfflineInbox()
      setHasOfflineInbox(inboxRes.data.length > 0)

      const historyRes = await chatAPI.getMessages(sessionId)
      setMessages(historyRes.data)
    } catch (err) {
      toast.error('加载消息失败')
      console.error(err)
    }
  }

  const handleCreateSession = async () => {
    try {
      const res = await chatAPI.createSession(`会话 ${new Date().toLocaleTimeString()}`)
      const nextSessions = [...sessions, res.data]
      setSessions(nextSessions)
      useChatStore.getState().setCurrentSession(res.data.session_id)
      toast.success('创建会话成功')
    } catch (err) {
      toast.error('创建会话失败')
      console.error(err)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      const nextSessions = sessions.filter((s) => s.session_id !== sessionId)
      setSessions(nextSessions)
      if (currentSessionId === sessionId) {
        useChatStore.getState().setCurrentSession(nextSessions[0]?.session_id ?? null)
        setMessages([])
      }
      toast.success('删除会话成功')
    } catch (err) {
      toast.error('删除会话失败')
      console.error(err)
    }
  }

  const handleOpenInbox = () => {
    if (hasOfflineInbox) {
      setHasOfflineInbox(false)
      toast.success('已查看离线信箱')
      return
    }
    toast('当前没有离线消息')
  }

  const handleTerminateTask = async (taskId: string) => {
    try {
      await auditAPI.killTask(taskId)
      toast.success(`任务 ${taskId} 已终止`)
      await loadManagedTasks()
    } catch (err) {
      toast.error('终止任务失败')
      console.error(err)
    }
  }

  return (
    <div className="flex h-screen bg-white">
      <SessionSidebar
        sessions={sessions}
        managedTasks={managedTasks}
        hasOfflineInbox={hasOfflineInbox}
        onInboxClick={handleOpenInbox}
        onTerminateTask={handleTerminateTask}
        onCreateSession={handleCreateSession}
        onDeleteSession={handleDeleteSession}
      />
      <ChatWindow />
    </div>
  )
}
