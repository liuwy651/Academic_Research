import { useState, useRef, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

  const handleLogout = () => {
    clearAuth()
    navigate('/login', { replace: true })
  }

  return (
    <div style={sidebarStyle}>
      {/* Header */}
      <div style={{ padding: '1rem', borderBottom: '1px solid #333' }}>
        <button
          onClick={() => createMutation.mutate('New Conversation')}
          disabled={createMutation.isPending}
          style={newChatBtnStyle}
        >
          + New Chat
        </button>
      </div>

      {/* Conversation list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 0' }}>
        {isLoading && <p style={mutedStyle}>Loading…</p>}
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
        {!isLoading && data?.items.length === 0 && (
          <p style={mutedStyle}>No conversations yet</p>
        )}
      </div>

      {/* Footer: user info + logout */}
      <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid #333', fontSize: '0.8rem' }}>
        <p style={{ margin: 0, color: '#ccc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {user?.full_name || user?.email}
        </p>
        <button onClick={handleLogout} style={logoutBtnStyle}>
          Sign Out
        </button>
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
  const [hovered, setHovered] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(conv.title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  const commitRename = () => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== conv.title) onRename(trimmed)
    else setDraft(conv.title)
    setEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') commitRename()
    if (e.key === 'Escape') { setDraft(conv.title); setEditing(false) }
  }

  return (
    <div
      style={{
        ...itemStyle,
        background: isActive ? '#2a2a2a' : hovered ? '#1e1e1e' : 'transparent',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => { if (!editing) onSelect() }}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          onClick={e => e.stopPropagation()}
          style={editInputStyle}
        />
      ) : (
        <>
          <span style={titleStyle}>{conv.title}</span>
          {(hovered || isActive) && (
            <div style={{ display: 'flex', gap: '0.2rem', flexShrink: 0 }}>
              <ActionBtn
                title="Rename"
                onClick={e => { e.stopPropagation(); setEditing(true) }}
              >
                ✎
              </ActionBtn>
              <ActionBtn
                title="Delete"
                onClick={e => { e.stopPropagation(); onDelete() }}
              >
                ✕
              </ActionBtn>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ActionBtn({
  children, onClick, title,
}: { children: React.ReactNode; onClick: React.MouseEventHandler; title: string }) {
  const [hov, setHov] = useState(false)
  return (
    <button
      title={title}
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? '#444' : 'transparent',
        border: 'none',
        color: '#aaa',
        cursor: 'pointer',
        padding: '2px 5px',
        borderRadius: 4,
        fontSize: '0.75rem',
      }}
    >
      {children}
    </button>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const sidebarStyle: React.CSSProperties = {
  width: '100%',
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  background: '#141414',
}

const newChatBtnStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.5rem',
  background: '#2a2a2a',
  border: '1px solid #444',
  borderRadius: 6,
  color: '#fff',
  cursor: 'pointer',
  fontSize: '0.875rem',
}

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '0.25rem',
  padding: '0.5rem 0.75rem',
  cursor: 'pointer',
  borderRadius: 6,
  margin: '0 0.25rem',
  transition: 'background 0.1s',
}

const titleStyle: React.CSSProperties = {
  flex: 1,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: '0.875rem',
}

const editInputStyle: React.CSSProperties = {
  flex: 1,
  background: '#333',
  border: '1px solid #555',
  borderRadius: 4,
  color: '#fff',
  padding: '2px 6px',
  fontSize: '0.875rem',
  outline: 'none',
}

const mutedStyle: React.CSSProperties = {
  color: '#555',
  fontSize: '0.8rem',
  textAlign: 'center',
  marginTop: '1rem',
}

const logoutBtnStyle: React.CSSProperties = {
  marginTop: '0.4rem',
  background: 'none',
  border: 'none',
  color: '#888',
  cursor: 'pointer',
  padding: 0,
  fontSize: '0.75rem',
}
