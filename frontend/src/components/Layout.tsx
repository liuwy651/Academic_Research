import { Outlet } from 'react-router-dom'
import ConversationSidebar from './ConversationSidebar'
import { ThemeToggle } from './ThemeToggle'

export default function Layout() {
  return (
    <div className="flex h-full overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <aside className="w-64 flex-shrink-0 border-r flex flex-col" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
        <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border-color)' }}>
          <h1 className="font-bold">Conversations</h1>
          <ThemeToggle />
        </div>
        <div className="flex-1 overflow-y-auto">
          <ConversationSidebar />
        </div>
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
