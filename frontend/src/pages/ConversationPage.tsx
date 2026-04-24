import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Bot, MessageSquare } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { conversationsApi } from '../api/conversations'
import type { LocalMessage } from '../types/message'

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>()
  const token = useAuthStore(s => s.token)

  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Load messages when conversation changes
  useEffect(() => {
    if (!id) return
    setMessages([])
    fetch(`/api/v1/conversations/${id}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then((data: LocalMessage[]) => setMessages(data))
      .catch(() => {/* ignore */})
  }, [id, token])

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
    }])

    try {
      const response = await fetch(`/api/v1/conversations/${id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content }),
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
    <div className="flex-1 flex flex-col overflow-hidden bg-[#0a0a0a]">
      {/* ── Header ── */}
      <ConversationHeader conversationId={id!} />

      {/* ── Message list ── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
          {messages.length === 0 && !isStreaming && <EmptyState />}
          {messages.map(msg => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Input area ── */}
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
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ConversationHeader({ conversationId }: { conversationId: string }) {
  const { data: conv } = useQuery({
    queryKey: ['conversations', conversationId],
    queryFn: () => conversationsApi.get(conversationId),
    enabled: !!conversationId,
  })

  return (
    <div className="flex items-center gap-2.5 px-5 py-3 border-b border-white/[0.06] bg-[#0e0e0e] flex-shrink-0">
      <MessageSquare className="w-4 h-4 text-[#3a3a3a] flex-shrink-0" />
      <span className="text-sm font-medium text-[#c0c0c0] truncate">
        {conv?.title ?? '…'}
      </span>
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
      {/* Assistant avatar */}
      <div className="w-7 h-7 bg-[#1a1a1a] border border-white/[0.08] rounded-lg
                      flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-3.5 h-3.5 text-violet-400" />
      </div>

      {/* Bubble */}
      <div className="flex-1 min-w-0">
        <div className="inline-block max-w-full bg-[#141414] border border-white/[0.06]
                        rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm text-[#d4d4d4] whitespace-pre-wrap leading-relaxed">
            {message.content || (streaming ? '' : '…')}
            {streaming && <span className="cursor-blink" />}
          </p>
        </div>
      </div>
    </div>
  )
}
