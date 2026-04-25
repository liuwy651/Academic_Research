import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, Bot, ChevronDown, ChevronRight, Code2, FileText, GitBranch, Globe, Loader2, MessageSquare, Paperclip, Sparkles, Square, Wrench, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useAuthStore } from '../store/authStore'
import { useConversationStore } from '../store/conversationStore'
import { conversationsApi } from '../api/conversations'
import { filesApi } from '../api/files'
import ConversationTree from '../components/ConversationTree'
import type { FileAttachmentInfo, LocalMessage, Message, ToolStep } from '../types/message'
import type { PendingFile } from '../types/file'

// ── Helpers ───────────────────────────────────────────────────────────────────

function toLocalMessages(data: Message[]): LocalMessage[] {
  return data.map(m => ({
    ...m,
    steps: m.tool_steps ?? undefined,
    thinkingDone: !!(m.thinking || m.tool_steps?.length),
  }))
}

function extractTokenStats(messages: LocalMessage[]) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.role === 'assistant' && m.context_tokens != null) {
      return { prompt: m.context_tokens, completion: 0, truncated: false }
    }
  }
  return null
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>()
  const token = useAuthStore(s => s.token)
  const queryClient = useQueryClient()
  const { activeNodeId, setActiveNodeId, isGenerating, startGenerating, stopGenerating } = useConversationStore()

  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [input, setInput] = useState('')
  const [showTree, setShowTree] = useState(true)
  const [treeWidth, setTreeWidth] = useState(280)
  const [tokenStats, setTokenStats] = useState<{
    prompt: number
    completion: number
    truncated: boolean
  } | null>(null)
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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
    setTokenStats(null)
    fetch(`/api/v1/conversations/${id}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then((data: Message[]) => {
        const local = toLocalMessages(data)
        setMessages(local)
        setTokenStats(extractTokenStats(local))
      })
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
      .then((data: Message[]) => {
        const local = toLocalMessages(data)
        setMessages(local)
        setTokenStats(extractTokenStats(local))
      })
      .catch(() => {})
  }, [id, token, setActiveNodeId])

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!id) return
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    for (const file of files) {
      const localId = `${Date.now()}-${Math.random()}`
      setPendingFiles(prev => [...prev, { localId, file, status: 'uploading' }])
      try {
        const resp = await filesApi.upload(id, file)
        setPendingFiles(prev =>
          prev.map(p => p.localId === localId ? { ...p, status: 'done', fileResponse: resp } : p)
        )
      } catch (err: any) {
        const msg = err?.response?.data?.detail ?? '上传失败'
        setPendingFiles(prev =>
          prev.map(p => p.localId === localId ? { ...p, status: 'error', error: msg } : p)
        )
      }
    }
  }

  const removePendingFile = (localId: string) => {
    setPendingFiles(prev => prev.filter(p => p.localId !== localId))
  }

  const sendMessage = async () => {
    const content = input.trim()
    if (!content || isGenerating || !id) return

    const controller = new AbortController()

    const fileIds = pendingFiles
      .filter(p => p.status === 'done' && p.fileResponse)
      .map(p => p.fileResponse!.id)

    setInput('')
    setPendingFiles([])
    startGenerating(controller)

    const attachedFiles: FileAttachmentInfo[] = pendingFiles
      .filter(p => p.status === 'done' && p.fileResponse)
      .map(p => ({
        id: p.fileResponse!.id,
        original_filename: p.fileResponse!.original_filename,
        file_type: p.fileResponse!.file_type,
        token_estimate: p.fileResponse!.token_estimate ?? null,
      }))

    const userMsg: LocalMessage = {
      id: `tmp-${Date.now()}`,
      conversation_id: id,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      parent_id: null,
      summary: null,
      context_tokens: null,
      files: attachedFiles,
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
      context_tokens: null,
      thinking: null,
      tool_steps: null,
      files: [],
    }])

    try {
      const response = await fetch(`/api/v1/conversations/${id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content, parent_id: activeNodeId, file_ids: fileIds }),
        signal: controller.signal,
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
            if (ev.type === 'thinking_chunk') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId
                  ? { ...m, thinking: (m.thinking ?? '') + ev.content }
                  : m
              ))
            } else if (ev.type === 'tool_start') {
              const newStep: ToolStep = { name: ev.name, args: ev.args ?? {}, status: 'running' }
              setMessages(prev => prev.map(m =>
                m.id === streamingId
                  ? { ...m, thinkingDone: true, steps: [...(m.steps ?? []), newStep] }
                  : m
              ))
            } else if (ev.type === 'tool_result') {
              setMessages(prev => prev.map(m => {
                if (m.id !== streamingId) return m
                const steps = [...(m.steps ?? [])]
                for (let i = steps.length - 1; i >= 0; i--) {
                  if (steps[i].name === ev.name && steps[i].status === 'running') {
                    steps[i] = { ...steps[i], result: ev.content, status: 'done' }
                    break
                  }
                }
                return { ...m, steps }
              }))
            } else if (ev.type === 'chunk') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId
                  ? { ...m, thinkingDone: true, content: m.content + ev.content }
                  : m
              ))
            } else if (ev.type === 'done') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId ? { ...m, id: ev.message_id, streaming: false } : m
              ))
              setActiveNodeId(ev.message_id)
              queryClient.invalidateQueries({ queryKey: ['tree', id] })
              if (ev.prompt_tokens != null) {
                setTokenStats({
                  prompt: ev.prompt_tokens,
                  completion: ev.completion_tokens ?? 0,
                  truncated: !!ev.context_truncated,
                })
              }
              // Update conversation title if auto-generated
              if (ev.title) {
                queryClient.setQueryData(['conversations', id], (old: any) =>
                  old ? { ...old, title: ev.title } : old
                )
                queryClient.invalidateQueries({ queryKey: ['conversations'] })
              }
            } else if (ev.type === 'error') {
              setMessages(prev => prev.map(m =>
                m.id === streamingId ? { ...m, content: `⚠ ${ev.detail}`, streaming: false } : m
              ))
            }
          } catch { /* ignore JSON parse errors */ }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // User stopped generation — keep partial content, just stop the cursor
        setMessages(prev => prev.map(m =>
          m.id === streamingId ? { ...m, streaming: false } : m
        ))
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to get response'
        setMessages(prev => prev.map(m =>
          m.id === streamingId ? { ...m, content: `⚠ ${msg}`, streaming: false } : m
        ))
      }
    } finally {
      stopGenerating()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
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
            {messages.length === 0 && !isGenerating && <EmptyState />}
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="flex-shrink-0 border-t border-white/[0.06] bg-[#0a0a0a] px-4 py-4">
          <div className="max-w-3xl mx-auto">
            {tokenStats && (
              <div className={`flex items-center gap-1.5 mb-2 text-[10px] ${
                tokenStats.truncated ? 'text-amber-500/70' : 'text-[#2e2e2e]'
              }`}>
                {tokenStats.truncated && <span>⚠</span>}
                <span>
                  {tokenStats.truncated
                    ? `上下文已截断 · 本次 ${tokenStats.prompt.toLocaleString()} tokens`
                    : `上下文 ${tokenStats.prompt.toLocaleString()} tokens`}
                </span>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.md,.markdown"
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />

            <div className="bg-[#111111] border border-white/[0.08] rounded-2xl px-4 py-3
                            focus-within:border-white/[0.16] transition-colors">
              {pendingFiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2.5">
                  {pendingFiles.map(pf => (
                    <FileChip key={pf.localId} pf={pf} onRemove={removePendingFile} />
                  ))}
                </div>
              )}
              <div className="flex items-end gap-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isGenerating}
                  title="Attach PDF or Markdown"
                  className="flex-shrink-0 w-7 h-7 flex items-center justify-center
                             text-[#3a3a3a] hover:text-violet-400 disabled:opacity-30
                             transition-colors cursor-pointer rounded-md hover:bg-white/[0.04]"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Message…"
                  disabled={isGenerating}
                  rows={1}
                  className="flex-1 bg-transparent text-sm text-[#f0f0f0] placeholder-[#3a3a3a]
                             resize-none outline-none min-h-[22px] max-h-[160px] leading-[22px]
                             disabled:opacity-50"
                />
                {isGenerating ? (
                  <button
                    onClick={stopGenerating}
                    title="Stop generating"
                    className="flex-shrink-0 w-8 h-8 bg-[#2a2a2a] hover:bg-[#383838]
                               rounded-lg flex items-center justify-center transition-colors cursor-pointer"
                  >
                    <Square className="w-3.5 h-3.5 text-white fill-white" />
                  </button>
                ) : (
                  <button
                    onClick={sendMessage}
                    disabled={!input.trim()}
                    className="flex-shrink-0 w-8 h-8 bg-violet-600 hover:bg-violet-500
                               disabled:opacity-25 disabled:cursor-not-allowed
                               rounded-lg flex items-center justify-center transition-colors cursor-pointer"
                  >
                    <ArrowUp className="w-4 h-4 text-white" />
                  </button>
                )}
              </div>
            </div>
            <p className="text-center text-[10px] text-[#282828] mt-2">
              Enter to send · Shift+Enter for new line · PDF/Markdown supported
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

// ── File chip ──────────────────────────────────────────────────────────────────

function FileChip({ pf, onRemove }: { pf: PendingFile; onRemove: (id: string) => void }) {
  const name = pf.file.name.length > 24 ? pf.file.name.slice(0, 22) + '…' : pf.file.name
  const tokenLabel = pf.fileResponse?.token_estimate
    ? ` · ~${pf.fileResponse.token_estimate.toLocaleString()} tokens`
    : ''

  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px] font-medium
      ${pf.status === 'error'
        ? 'bg-red-500/10 text-red-400 border border-red-500/20'
        : 'bg-violet-500/10 text-violet-300 border border-violet-500/20'
      }`}
    >
      {pf.status === 'uploading' ? (
        <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
      ) : (
        <FileText className="w-3 h-3 flex-shrink-0" />
      )}
      <span className="max-w-[160px] truncate">
        {pf.status === 'error' ? `${name} — ${pf.error}` : `${name}${tokenLabel}`}
      </span>
      {pf.status !== 'uploading' && (
        <button
          onClick={() => onRemove(pf.localId)}
          className="ml-0.5 opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
        >
          <X className="w-3 h-3" />
        </button>
      )}
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
  img({ src, alt }: any) { return <ZoomableImage src={src ?? ''} alt={alt} /> },
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: LocalMessage }) {
  const isUser = message.role === 'user'
  const streaming = !!message.streaming

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[72%] flex flex-col items-end gap-1.5">
          {message.files && message.files.length > 0 && (
            <div className="flex flex-wrap gap-1.5 justify-end">
              {message.files.map(f => (
                <div
                  key={f.id}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                             bg-violet-800/60 border border-violet-500/30
                             text-[11px] text-violet-200"
                >
                  <FileText className="w-3 h-3 flex-shrink-0 opacity-80" />
                  <span className="max-w-[160px] truncate">{f.original_filename}</span>
                  {f.token_estimate != null && (
                    <span className="opacity-50 tabular-nums">
                      ~{f.token_estimate.toLocaleString()}t
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          <div className="bg-violet-600 text-white text-sm px-4 py-3
                          rounded-2xl rounded-tr-sm leading-relaxed">
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
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
          {(message.thinking || !!message.steps?.length) && (
            <ReasoningPanel
              thinking={message.thinking ?? undefined}
              thinkingDone={!!message.thinkingDone}
              steps={message.steps}
              streaming={!!message.streaming}
            />
          )}

          <div className="text-sm text-[#d4d4d4] leading-relaxed">
            {message.content ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={mdComponents}
              >
                {message.content}
              </ReactMarkdown>
            ) : (
              !streaming && !message.thinking && <span className="text-[#4a4a4a]">…</span>
            )}
            {streaming && !!message.thinkingDone && <span className="cursor-blink" />}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Reasoning panel (unified thinking + tool steps) ───────────────────────────

function getStepLabel(name: string): string {
  if (name === 'execute_bocha_search') return '网络搜索'
  if (name === 'execute_python_code') return '运行 Python'
  if (name.startsWith('fs__')) return '文件系统'
  return name
}

function getStepSummary(step: ToolStep): string {
  if (step.name === 'execute_bocha_search') {
    const q = step.args.query as string | undefined
    return q ? (q.length > 50 ? q.slice(0, 50) + '…' : q) : ''
  }
  if (step.name === 'execute_python_code') {
    const code = (step.args.code as string | undefined) ?? ''
    const first = code.split('\n').find(l => l.trim()) ?? ''
    return first.length > 50 ? first.slice(0, 50) + '…' : first
  }
  const entries = Object.entries(step.args)
  if (!entries.length) return ''
  const [k, v] = entries[0]
  const vs = typeof v === 'string' ? v : JSON.stringify(v)
  const s = `${k}: ${vs}`
  return s.length > 50 ? s.slice(0, 50) + '…' : s
}

function ToolStepRow({ step }: { step: ToolStep }) {
  const [open, setOpen] = useState(false)
  const isRunning = step.status === 'running'
  const label = getStepLabel(step.name)
  const summary = getStepSummary(step)
  const Icon = step.name === 'execute_bocha_search' ? Globe
    : step.name === 'execute_python_code' ? Code2
    : Wrench

  return (
    <div>
      <button
        onClick={() => step.result && setOpen(o => !o)}
        disabled={!step.result}
        className="flex items-center gap-2 w-full text-left px-2 py-1 rounded-md
                   hover:bg-white/[0.04] transition-colors disabled:cursor-default"
      >
        {isRunning
          ? <Loader2 className="w-3 h-3 text-violet-400 animate-spin flex-shrink-0" />
          : <Icon className="w-3 h-3 text-violet-400/50 flex-shrink-0" />
        }
        <span className={`text-[11px] font-medium flex-shrink-0 ${isRunning ? 'text-violet-300/80' : 'text-[#505050]'}`}>
          {label}
        </span>
        {summary && (
          <span className="text-[11px] text-[#363636] truncate">{summary}</span>
        )}
        {step.result && (
          <span className="ml-auto flex-shrink-0">
            {open
              ? <ChevronDown className="w-3 h-3 text-[#383838]" />
              : <ChevronRight className="w-3 h-3 text-[#383838]" />
            }
          </span>
        )}
      </button>
      {open && step.result && (
        <pre className="mx-2 mt-0.5 mb-1 text-[10px] text-[#646464] bg-[#0a0a0a]
                        border border-white/[0.05] rounded-lg px-3 py-2
                        overflow-x-auto whitespace-pre-wrap break-words
                        max-h-48 overflow-y-auto leading-relaxed">
          {step.result}
        </pre>
      )}
    </div>
  )
}

function ReasoningPanel({
  thinking,
  thinkingDone,
  steps,
  streaming,
}: {
  thinking?: string
  thinkingDone: boolean
  steps?: ToolStep[]
  streaming: boolean
}) {
  const [open, setOpen] = useState(false)
  const revealedRef = useRef(false)

  // Expand when thinking finishes for the first time
  useEffect(() => {
    if (thinkingDone && !revealedRef.current) {
      setOpen(true)
      revealedRef.current = true
    }
  }, [thinkingDone])

  // Collapse when streaming ends
  useEffect(() => {
    if (!streaming && revealedRef.current) {
      setOpen(false)
    }
  }, [streaming])

  const hasSteps = !!steps?.length

  // While thinking is still in progress: show live thinking text
  if (!thinkingDone) {
    return (
      <div className="mb-3 rounded-xl border border-amber-700/[0.14] bg-amber-900/[0.06] overflow-hidden">
        <div className="flex items-center gap-2 px-2.5 py-2">
          <Sparkles className="w-3 h-3 text-amber-400/70 animate-pulse flex-shrink-0" />
          <span className="text-[11px] text-amber-300/50 font-medium">思考中…</span>
          {thinking && (
            <span className="text-[10px] text-amber-800/60 font-mono tabular-nums">
              {thinking.length} 字
            </span>
          )}
        </div>
        {thinking && (
          <div className="px-3 pb-2.5 max-h-48 overflow-y-auto">
            <p className="text-[11px] font-mono text-amber-100/20 leading-relaxed whitespace-pre-wrap break-words">
              {thinking}
            </p>
          </div>
        )}
      </div>
    )
  }

  // Nothing to show
  if (!thinking && !hasSteps) return null

  const thinkingLen = thinking?.length ?? 0
  const toolCount = steps?.length ?? 0

  return (
    <div className="mb-3 rounded-xl border border-white/[0.07] bg-[#0c0c0a] overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left
                   hover:bg-white/[0.03] transition-colors"
      >
        <Sparkles className="w-3 h-3 text-amber-600/40 flex-shrink-0" />
        <span className="text-[11px] font-medium text-[#3a3828]">推理过程</span>
        <span className="text-[10px] text-[#2a2820] font-mono">
          {thinkingLen > 0 && `${thinkingLen}字`}
          {thinkingLen > 0 && toolCount > 0 && ' · '}
          {toolCount > 0 && `${toolCount}个工具`}
        </span>
        <span className="ml-auto flex-shrink-0">
          {open
            ? <ChevronDown className="w-3 h-3 text-[#2a2820]" />
            : <ChevronRight className="w-3 h-3 text-[#2a2820]" />
          }
        </span>
      </button>

      {open && (
        <div className="border-t border-white/[0.05]">
          {/* Thinking text */}
          {thinking && (
            <div className={`px-3 py-2.5 ${hasSteps ? 'border-b border-white/[0.04]' : ''}`}>
              <p className="text-[11px] font-mono text-amber-100/20
                            leading-relaxed whitespace-pre-wrap break-words">
                {thinking}
              </p>
            </div>
          )}

          {/* Tool steps */}
          {hasSteps && (
            <div className="px-1.5 py-1.5 space-y-0.5">
              {steps!.map((step, i) => (
                <ToolStepRow key={i} step={step} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Zoomable image — used by mdComponents.img ─────────────────────────────────

function ZoomableImage({ src, alt }: { src: string; alt?: string }) {
  const [zoomed, setZoomed] = useState(false)

  return (
    <>
      <img
        src={src}
        alt={alt ?? ''}
        onClick={() => setZoomed(true)}
        className="max-w-full rounded-lg shadow-md border border-white/[0.08]
                   cursor-zoom-in hover:border-violet-500/40 transition-colors my-2"
      />
      {zoomed && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center
                     bg-black/80 backdrop-blur-sm"
          onClick={() => setZoomed(false)}
        >
          <img
            src={src}
            alt={alt ?? ''}
            className="max-w-[90vw] max-h-[90vh] rounded-xl shadow-2xl
                       border border-white/10 cursor-zoom-out"
            onClick={e => e.stopPropagation()}
          />
          <button
            onClick={() => setZoomed(false)}
            className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center
                       rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </>
  )
}
