import { Outlet } from 'react-router-dom'
import ConversationSidebar from './ConversationSidebar'

export default function Layout() {
  return (
    <div className="flex h-full bg-[#0a0a0a] text-[#f5f5f5] overflow-hidden">
      <aside className="w-64 flex-shrink-0 border-r border-white/[0.06] bg-[#111111]">
        <ConversationSidebar />
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
