import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, LogOut, MessageSquare, Pencil, Plus, Trash2 } from 'lucide-react'
import { conversationsApi } from '../api/conversations'
import { useAuthStore } from '../store/authStore'
import type { Conversation } from '../types/conversation'

export default function ConversationSidebar() {
  const navigate = useNavigate()
  const { id: activeId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { user, clearAuth } = useAuthStore()

  const { data, isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationsApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: conversationsApi.create,
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/conversations/${conv.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: conversationsApi.delete,
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (activeId === deletedId) navigate('/')
    },
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      conversationsApi.update(id, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  })

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.slice(0, 2).toUpperCase() ?? 'U'

  return (
    <div className="flex flex-col h-full">

      {/* ── Header ── */}
      <div className="px-3 pt-4 pb-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5 px-1 mb-3">
          <div className="w-6 h-6 bg-violet-600 rounded-md flex items-center justify-center flex-shrink-0">
            <Bot className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-sm font-semibold text-white tracking-tight">Agent</span>
        </div>

        <button
          onClick={() => createMutation.mutate('New Conversation')}
          disabled={createMutation.isPending}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-[#a3a3a3] hover:text-white
                     border border-white/[0.07] hover:border-white/[0.14] rounded-md
                     hover:bg-white/[0.04] transition-all disabled:opacity-40 cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" />
          New Chat
        </button>
      </div>

      {/* ── Conversation list ── */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {isLoading && (
          <p className="text-center text-xs text-[#3f3f3f] py-6">Loading…</p>
        )}

        {!isLoading && data?.items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 gap-2">
            <MessageSquare className="w-6 h-6 text-[#2a2a2a]" />
            <p className="text-xs text-[#3f3f3f]">No conversations yet</p>
          </div>
        )}

        {data?.items.map((conv) => (
          <ConversationItem
            key={conv.id}
            conv={conv}
            isActive={conv.id === activeId}
            onSelect={() => navigate(`/conversations/${conv.id}`)}
            onRename={(title) => renameMutation.mutate({ id: conv.id, title })}
            onDelete={() => deleteMutation.mutate(conv.id)}
          />
        ))}
      </div>

      {/* ── Footer: user ── */}
      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-white/[0.04] transition-colors group cursor-default">
          <div className="w-6 h-6 rounded-full bg-violet-500/15 border border-violet-500/25 flex items-center justify-center text-[10px] font-semibold text-violet-400 flex-shrink-0">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-[#d4d4d4] truncate leading-none mb-0.5">
              {user?.full_name || user?.email}
            </p>
            {user?.full_name && (
              <p className="text-[10px] text-[#525252] truncate leading-none">{user.email}</p>
            )}
          </div>
          <button
            onClick={() => { clearAuth(); navigate('/login', { replace: true }) }}
            title="Sign out"
            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/[0.08]
                       text-[#525252] hover:text-[#a3a3a3] transition-all cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── ConversationItem ───────────────────────────────────────────────────────────

type ItemProps = {
  conv: Conversation
  isActive: boolean
  onSelect: () => void
  onRename: (title: string) => void
  onDelete: () => void
}

function ConversationItem({ conv, isActive, onSelect, onRename, onDelete }: ItemProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(conv.title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { if (editing) inputRef.current?.select() }, [editing])

  const commitRename = () => {
    const t = draft.trim()
    if (t && t !== conv.title) onRename(t)
    else setDraft(conv.title)
    setEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') commitRename()
    if (e.key === 'Escape') { setDraft(conv.title); setEditing(false) }
  }

  return (
    <div
      onClick={() => { if (!editing) onSelect() }}
      className={`
        flex items-center gap-1.5 px-2 py-1.5 rounded-md cursor-pointer group text-xs transition-colors
        ${isActive
          ? 'bg-white/[0.07] text-white'
          : 'text-[#8a8a8a] hover:bg-white/[0.04] hover:text-[#d4d4d4]'}
      `}
    >
      <MessageSquare className="w-3 h-3 flex-shrink-0 text-[#404040]" />

      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          onClick={e => e.stopPropagation()}
          className="flex-1 bg-transparent text-white outline-none text-xs min-w-0"
        />
      ) : (
        <>
          <span className="flex-1 truncate">{conv.title}</span>
          <div className="opacity-0 group-hover:opacity-100 flex gap-0.5 flex-shrink-0">
            <ActionBtn label="Rename" onClick={e => { e.stopPropagation(); setEditing(true) }}>
              <Pencil className="w-3 h-3" />
            </ActionBtn>
            <ActionBtn
              label="Delete"
              danger
              onClick={e => { e.stopPropagation(); onDelete() }}
            >
              <Trash2 className="w-3 h-3" />
            </ActionBtn>
          </div>
        </>
      )}
    </div>
  )
}

function ActionBtn({
  children, onClick, label, danger = false,
}: {
  children: React.ReactNode
  onClick: React.MouseEventHandler
  label: string
  danger?: boolean
}) {
  return (
    <button
      title={label}
      onClick={onClick}
      className={`p-1 rounded transition-colors cursor-pointer
        ${danger
          ? 'text-[#525252] hover:text-red-400 hover:bg-red-500/10'
          : 'text-[#525252] hover:text-[#a3a3a3] hover:bg-white/[0.08]'}`}
    >
      {children}
    </button>
  )
}
