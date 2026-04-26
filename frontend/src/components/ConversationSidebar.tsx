import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Database, LogOut, MessageSquare, Pencil, Plus, Trash2 } from 'lucide-react'
import { conversationsApi } from '../api/conversations'
import { useAuthStore } from '../store/authStore'
import type { Conversation } from '../types/conversation'

export default function ConversationSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { id: activeId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { user, clearAuth } = useAuthStore()
  const isKbActive = location.pathname.startsWith('/knowledge-bases')

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
      <div className="px-3 pt-4 pb-3 border-b" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-center gap-2.5 px-1 mb-3">
          <div className="w-6 h-6 bg-violet-600 rounded-md flex items-center justify-center flex-shrink-0">
            <Bot className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-sm font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Agent</span>
        </div>

        <button
          onClick={() => createMutation.mutate('New Conversation')}
          disabled={createMutation.isPending}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs rounded-md transition-all disabled:opacity-40 cursor-pointer"
          style={{
            color: 'var(--text-tertiary)',
            border: `1px solid var(--border-subtle)`,
            backgroundColor: 'transparent'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--text-primary)'
            e.currentTarget.style.borderColor = 'var(--border-color)'
            e.currentTarget.style.backgroundColor = 'var(--hover-bg)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-tertiary)'
            e.currentTarget.style.borderColor = 'var(--border-subtle)'
            e.currentTarget.style.backgroundColor = 'transparent'
          }}
        >
          <Plus className="w-3.5 h-3.5" />
          New Chat
        </button>
      </div>

      {/* ── Knowledge Base nav ── */}
      <div className="px-2 py-2 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        <button
          onClick={() => navigate('/knowledge-bases')}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs rounded-md transition-all cursor-pointer"
          style={{
            backgroundColor: isKbActive ? 'var(--active-bg)' : 'transparent',
            color: isKbActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
          }}
          onMouseEnter={e => {
            if (!isKbActive) {
              e.currentTarget.style.backgroundColor = 'var(--hover-bg)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }
          }}
          onMouseLeave={e => {
            if (!isKbActive) {
              e.currentTarget.style.backgroundColor = 'transparent'
              e.currentTarget.style.color = 'var(--text-tertiary)'
            }
          }}
        >
          <Database className="w-3.5 h-3.5 flex-shrink-0" />
          Knowledge Base
        </button>
      </div>

      {/* ── Conversation list ── */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {isLoading && (
          <p className="text-center text-xs py-6" style={{ color: 'var(--text-muted)' }}>Loading…</p>
        )}

        {!isLoading && data?.items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 gap-2">
            <MessageSquare className="w-6 h-6" style={{ color: 'var(--text-tertiary)' }} />
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No conversations yet</p>
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
      <div className="border-t p-3" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg transition-colors group cursor-default" style={{ backgroundColor: 'transparent' }} onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--hover-bg)' }} onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}>
          <div className="w-6 h-6 rounded-full bg-violet-500/15 border border-violet-500/25 flex items-center justify-center text-[10px] font-semibold text-violet-400 flex-shrink-0">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate leading-none mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              {user?.full_name || user?.email}
            </p>
            {user?.full_name && (
              <p className="text-[10px] truncate leading-none" style={{ color: 'var(--text-muted)' }}>{user.email}</p>
            )}
          </div>
          <button
            onClick={() => { clearAuth(); navigate('/login', { replace: true }) }}
            title="Sign out"
            className="opacity-0 group-hover:opacity-100 p-1 rounded transition-all cursor-pointer"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--text-tertiary)'
              e.currentTarget.style.backgroundColor = 'var(--hover-bg)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--text-muted)'
              e.currentTarget.style.backgroundColor = 'transparent'
            }}
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
      className="flex items-center gap-1.5 px-2 py-1.5 rounded-md cursor-pointer group text-xs transition-colors"
      style={{
        backgroundColor: isActive ? 'var(--active-bg)' : 'transparent',
        color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
      }}
      onMouseEnter={(e) => {
        if (!isActive) {
          e.currentTarget.style.backgroundColor = 'var(--hover-bg)'
          e.currentTarget.style.color = 'var(--text-secondary)'
        }
      }}
      onMouseLeave={(e) => {
        if (!isActive) {
          e.currentTarget.style.backgroundColor = 'transparent'
          e.currentTarget.style.color = 'var(--text-tertiary)'
        }
      }}
    >
      <MessageSquare className="w-3 h-3 flex-shrink-0" style={{ color: 'var(--icon-secondary)' }} />

      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          onClick={e => e.stopPropagation()}
          className="flex-1 bg-transparent outline-none text-xs min-w-0"
          style={{ color: 'var(--text-primary)' }}
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
      className="p-1 rounded transition-colors cursor-pointer"
      style={{
        color: danger ? '#ef4444' : 'var(--text-muted)',
        backgroundColor: 'transparent',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = danger ? '#ff6b6b' : 'var(--text-tertiary)'
        e.currentTarget.style.backgroundColor = danger ? 'rgba(239, 68, 68, 0.1)' : 'var(--hover-bg)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = danger ? '#ef4444' : 'var(--text-muted)'
        e.currentTarget.style.backgroundColor = 'transparent'
      }}
    >
      {children}
    </button>
  )
}
