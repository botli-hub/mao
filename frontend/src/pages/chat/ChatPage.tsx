import React, { useEffect } from 'react'
import { useChatStore } from '../../stores'
import { chatAPI } from '../../api/services'
import { ChatWindow } from '../../components/chat/ChatWindow'
import { SessionSidebar } from '../../components/chat/SessionSidebar'
import toast from 'react-hot-toast'

export function ChatPage() {
  const { sessions, setSessions, setMessages } = useChatStore()

  useEffect(() => {
    loadSessions()
  }, [])

  const loadSessions = async () => {
    try {
      const res = await chatAPI.getSessions()
      setSessions(res.data.items)
    } catch (err) {
      toast.error('加载会话失败')
      console.error(err)
    }
  }

  const handleCreateSession = async () => {
    try {
      const res = await chatAPI.createSession(`会话 ${new Date().toLocaleTimeString()}`)
      setSessions([...sessions, res.data])
      toast.success('创建会话成功')
    } catch (err) {
      toast.error('创建会话失败')
      console.error(err)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      setSessions(sessions.filter((s) => s.session_id !== sessionId))
      setMessages([])
      toast.success('删除会话成功')
    } catch (err) {
      toast.error('删除会话失败')
      console.error(err)
    }
  }

  return (
    <div className="flex h-screen bg-white">
      <SessionSidebar
        sessions={sessions}
        onCreateSession={handleCreateSession}
        onDeleteSession={handleDeleteSession}
      />
      <ChatWindow />
    </div>
  )
}
