import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { ChatPage } from './pages/chat/ChatPage'
import { AdminDashboard } from './pages/admin/AdminDashboard'

export function App() {
  return (
    <Router>
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
      </Routes>
      <Toaster position="top-right" />
    </Router>
  )
}

export default App
