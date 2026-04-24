import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, Bot, GitBranch, MessageSquare } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useAuthStore } from '../store/authStore'
import { useConversationStore } from '../store/conversationStore'
import { conversationsApi } from '../api/conversations'
import ConversationTree from '../components/ConversationTree'
import type { LocalMessage } from '../types/message'

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>()
  const token = useAuthStore(s => s.token)
  const queryClient = useQueryClient()
  const { activeNodeId, setActiveNodeId } = useConversationStore()

  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [showTree, setShowTree] = useState(true)
  const [treeWidth, setTreeWidth] = useState(280)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Drag left edge of tree sidebar to resize
  const onResizeDragDown = (e: React.MouseEvent) => {
    e.preventDefault()
    const sx = e.clientX, ow = treeWidth
    const onMove = (ev: MouseEvent) =>
      setTreeWidth(Math.max(180, Math.min(560, ow - (ev.clientX - sx))))
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  // Load messages when conversation changes (clears active node)
  useEffect(() => {
    if (!id || !token) return
    setActiveNodeId(null)
    setMessages([])
    fetch(`/api/v1/conversations/${id}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then((data: LocalMessage[]) => setMessages(data))
      .catch(() => {})
  }, [id, token]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Textarea auto-resize
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  // Called when user clicks a tree node — reload the linear path to that node
  const handleNodeClick = useCallback((nodeId: string) => {
    if (!id || !token) return
    setActiveNodeId(nodeId)
    setMessages([])
    fetch(`/api/v1/conversations/${id}/messages?node_id=${nodeId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then((data: LocalMessage[]) => setMessages(data))
      .catch(() => {})
  }, [id, token, setActiveNodeId])

  const sendMessage = async () => {
    const content = input.trim()
    if (!content || isStreaming || !id) return

    setInput('')
    setIsStreaming(true)

    const userMsg: LocalMessage = {
      id: `tmp-${Date.now()}`,
      conversation_id: id,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      parent_id: null,
      summary: null,
    }
    setMessages(prev => [...prev, userMsg])

    const streamingId = `streaming-${Date.now()}`
    setMessages(prev => [...prev, {
      id: streamingId,
      conversation_id: id,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      streaming: true,
      parent_id: null,
      summary: null,
    }])

    try {
      const response = await fetch(`/api/v1/conversations/${id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content, parent_id: activeNodeId }),
      })

      if (!response.ok || !response.body) {
        const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
        throw new Error(err.detail ?? `HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const dataLine = part.split('\n').find(l => l.startsWith('data: '))
          if (!dataLine) continue
          const jsonStr = dataLine.slice(6).trim()
          if (!jsonStr) continue
          try {
            const ev = JSON.parse(jsonStr)
            if (ev.type === 'chunk') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId ? { ...m, content: m.content + ev.content } : m
              ))
            } else if (ev.type === 'done') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId ? { ...m, id: ev.message_id, streaming: false } : m
              ))
              // Track the new leaf node and refresh the tree
              setActiveNodeId(ev.message_id)
              queryClient.invalidateQueries({ queryKey: ['tree', id] })
            } else if (ev.type === 'error') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId ? { ...m, content: `⚠ ${ev.detail}`, streaming: false } : m
              ))
            }
          } catch { /* ignore JSON parse errors */ }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to get response'
      setMessages(prev => prev.map(m =>
        m.id === streamingId ? { ...m, content: `⚠ ${msg}`, streaming: false } : m
      ))
    } finally {
      setIsStreaming(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Main chat column ── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[#0a0a0a] min-w-0">
        <ConversationHeader
          conversationId={id!}
          showTree={showTree}
          onToggleTree={() => setShowTree(v => !v)}
        />

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            {messages.length === 0 && !isStreaming && <EmptyState />}
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="flex-shrink-0 border-t border-white/[0.06] bg-[#0a0a0a] px-4 py-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-3 bg-[#111111] border border-white/[0.08] rounded-2xl px-4 py-3
                            focus-within:border-white/[0.16] transition-colors">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message…"
                disabled={isStreaming}
                rows={1}
                className="flex-1 bg-transparent text-sm text-[#f0f0f0] placeholder-[#3a3a3a]
                           resize-none outline-none min-h-[22px] max-h-[160px] leading-[22px]
                           disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || isStreaming}
                className="flex-shrink-0 w-8 h-8 bg-violet-600 hover:bg-violet-500
                           disabled:opacity-25 disabled:cursor-not-allowed
                           rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              >
                <ArrowUp className="w-4 h-4 text-white" />
              </button>
            </div>
            <p className="text-center text-[10px] text-[#282828] mt-2">
              Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>

      {/* ── Right tree sidebar ── */}
      {showTree && id && (
        <div
          className="flex-shrink-0 flex relative border-l border-white/[0.06] bg-[#0e0e0e] overflow-hidden"
          style={{ width: treeWidth }}
        >
          {/* Drag handle on left edge */}
          <div
            onMouseDown={onResizeDragDown}
            className="absolute left-0 top-0 bottom-0 w-1 cursor-ew-resize z-10
                       hover:bg-violet-500/30 transition-colors"
          />
          <div className="flex-1 overflow-hidden">
            <ConversationTree
              convId={id}
              activeNodeId={activeNodeId}
              onSelectNode={handleNodeClick}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ConversationHeader({
  conversationId,
  showTree,
  onToggleTree,
}: {
  conversationId: string
  showTree: boolean
  onToggleTree: () => void
}) {
  const { data: conv } = useQuery({
    queryKey: ['conversations', conversationId],
    queryFn: () => conversationsApi.get(conversationId),
    enabled: !!conversationId,
  })

  return (
    <div className="flex items-center gap-2.5 px-5 py-3 border-b border-white/[0.06] bg-[#0e0e0e] flex-shrink-0">
      <MessageSquare className="w-4 h-4 text-[#3a3a3a] flex-shrink-0" />
      <span className="flex-1 text-sm font-medium text-[#c0c0c0] truncate">
        {conv?.title ?? '…'}
      </span>
      <button
        onClick={onToggleTree}
        title="Toggle tree view"
        className={`flex items-center justify-center w-7 h-7 rounded-md transition-colors cursor-pointer
          ${showTree
            ? 'bg-violet-600/20 text-violet-400'
            : 'text-[#3a3a3a] hover:text-white/50 hover:bg-white/[0.04]'
          }`}
      >
        <GitBranch className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="w-12 h-12 bg-white/[0.03] border border-white/[0.06] rounded-2xl
                      flex items-center justify-center">
        <Bot className="w-5 h-5 text-violet-500" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-[#8a8a8a]">How can I help you today?</p>
        <p className="text-xs text-[#3a3a3a]">Send a message to start the conversation</p>
      </div>
    </div>
  )
}

// ── Markdown renderer config ───────────────────────────────────────────────────

const mdComponents = {
  pre({ children }: any) { return <>{children}</> },
  code({ className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || '')
    return match ? (
      <SyntaxHighlighter
        PreTag="div"
        language={match[1]}
        style={vscDarkPlus}
        customStyle={{ background: '#0d0d0d', borderRadius: '8px', padding: '12px 14px', margin: '6px 0', fontSize: '12px', lineHeight: '1.6' }}
      >
        {String(children).replace(/\n$/, '')}
      </SyntaxHighlighter>
    ) : (
      <code className="bg-[#1e1e1e] text-violet-300 px-1.5 py-0.5 rounded text-[0.85em] font-mono" {...props}>
        {children}
      </code>
    )
  },
  p({ children }: any) { return <p className="mb-2 last:mb-0 leading-relaxed">{children}</p> },
  h1({ children }: any) { return <h1 className="text-base font-semibold mb-2 mt-3 first:mt-0 text-[#e8e8e8]">{children}</h1> },
  h2({ children }: any) { return <h2 className="text-sm font-semibold mb-2 mt-3 first:mt-0 text-[#e0e0e0]">{children}</h2> },
  h3({ children }: any) { return <h3 className="text-sm font-medium mb-1 mt-2 first:mt-0">{children}</h3> },
  ul({ children }: any) { return <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul> },
  ol({ children }: any) { return <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol> },
  li({ children }: any) { return <li className="leading-relaxed">{children}</li> },
  blockquote({ children }: any) {
    return (
      <blockquote className="border-l-2 border-violet-500/40 pl-3 my-2 text-[#8a8a8a] italic">
        {children}
      </blockquote>
    )
  },
  a({ href, children }: any) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer"
         className="text-violet-400 hover:text-violet-300 underline underline-offset-2 transition-colors">
        {children}
      </a>
    )
  },
  table({ children }: any) {
    return <div className="overflow-x-auto my-2"><table className="text-xs border-collapse w-full">{children}</table></div>
  },
  thead({ children }: any) { return <thead className="border-b border-white/[0.1]">{children}</thead> },
  th({ children }: any) { return <th className="text-left px-3 py-1.5 font-medium text-[#a0a0a0]">{children}</th> },
  tr({ children }: any) { return <tr className="border-b border-white/[0.04]">{children}</tr> },
  td({ children }: any) { return <td className="px-3 py-1.5">{children}</td> },
  hr() { return <hr className="border-white/[0.08] my-3" /> },
  strong({ children }: any) { return <strong className="font-semibold text-[#e8e8e8]">{children}</strong> },
  em({ children }: any) { return <em className="italic text-[#c8c8c8]">{children}</em> },
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: LocalMessage }) {
  const isUser = message.role === 'user'
  const streaming = !!message.streaming

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[72%] bg-violet-600 text-white text-sm px-4 py-3
                        rounded-2xl rounded-tr-sm leading-relaxed">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 items-start">
      <div className="w-7 h-7 bg-[#1a1a1a] border border-white/[0.08] rounded-lg
                      flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-3.5 h-3.5 text-violet-400" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="bg-[#141414] border border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-3">
          <div className="text-sm text-[#d4d4d4] leading-relaxed">
            {message.content ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                {message.content}
              </ReactMarkdown>
            ) : (
              !streaming && <span className="text-[#4a4a4a]">…</span>
            )}
            {streaming && <span className="cursor-blink" />}
          </div>
        </div>
      </div>
    </div>
  )
}
