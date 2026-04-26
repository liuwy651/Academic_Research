import { Routes, Route, Navigate } from 'react-router-dom'
import PrivateRoute from './components/PrivateRoute'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import ConversationPage from './pages/ConversationPage'
import KnowledgeBasePage from './pages/KnowledgeBasePage'
import KnowledgeBaseDetailPage from './pages/KnowledgeBaseDetailPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected layout with sidebar */}
      <Route
        path="/"
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="conversations/:id" element={<ConversationPage />} />
        <Route path="knowledge-bases" element={<KnowledgeBasePage />} />
        <Route path="knowledge-bases/:id" element={<KnowledgeBaseDetailPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
