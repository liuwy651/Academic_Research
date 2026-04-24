import { Outlet } from 'react-router-dom'
import ConversationSidebar from './ConversationSidebar'

export default function Layout() {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#1a1a1a' }}>
      <aside style={{ width: 260, flexShrink: 0, borderRight: '1px solid #2a2a2a' }}>
        <ConversationSidebar />
      </aside>
      <main style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </main>
    </div>
  )
}
