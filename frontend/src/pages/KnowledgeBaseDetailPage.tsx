import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, CheckCircle, ChevronDown, ChevronRight,
  Database, FileText, Loader2, Trash2, Upload, XCircle,
} from 'lucide-react'
import { knowledgeBaseApi } from '../api/knowledgeBase'
import type { KBDocument } from '../types/knowledgeBase'

// ── 状态徽章 ─────────────────────────────────────────────────────────

function StatusBadge({ doc }: { doc: KBDocument }) {
  if (doc.status === 'completed') {
    return (
      <span className="flex items-center gap-1 text-xs" style={{ color: '#22c55e' }}>
        <CheckCircle className="w-3.5 h-3.5" />
        完成 {doc.chunk_count != null ? `· ${doc.chunk_count} 块` : ''}
      </span>
    )
  }
  if (doc.status === 'processing') {
    return (
      <span className="flex items-center gap-1 text-xs" style={{ color: '#f59e0b' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        解析中…
      </span>
    )
  }
  if (doc.status === 'pending') {
    return (
      <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
        <span className="w-2 h-2 rounded-full bg-current" />
        等待处理
      </span>
    )
  }
  return (
    <span
      className="flex items-center gap-1 text-xs cursor-help"
      style={{ color: '#ef4444' }}
      title={doc.error_message ?? '未知错误'}
    >
      <XCircle className="w-3.5 h-3.5" />
      失败
    </span>
  )
}

// ── 切块预览面板 ──────────────────────────────────────────────────────

function ChunkPanel({ kbId, docId, chunkCount }: { kbId: string; docId: string; chunkCount?: number | null }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['kb-chunks', kbId, docId],
    queryFn: () => knowledgeBaseApi.getChunks(kbId, docId),
    staleTime: Infinity,   // 切块不会变，缓存永久有效
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-4 h-4 animate-spin mr-2" style={{ color: 'var(--text-muted)' }} />
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>加载切块…</span>
      </div>
    )
  }

  if (isError) {
    return (
      <p className="text-xs py-4 text-center" style={{ color: '#ef4444' }}>切块加载失败，请重试</p>
    )
  }

  const chunks = data?.chunks ?? []
  const isParent = data?.level === 'parent'

  return (
    <>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {isParent ? '段落预览' : '切块预览'}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {isParent
            ? `共 ${chunks.length} 段${chunkCount != null ? `（${chunkCount} 个检索块）` : ''}`
            : `共 ${chunks.length} 块`}
        </span>
      </div>
    <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
      {chunks.map(chunk => (
        <div
          key={chunk.index}
          className="rounded-lg px-3 py-2.5"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-subtle)' }}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}
            >
              {isParent ? `段落 ${chunk.index + 1}` : `#${chunk.index + 1}`}
            </span>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {chunk.content.length} 字符
            </span>
          </div>
          <p className="text-xs leading-relaxed whitespace-pre-wrap break-words" style={{ color: 'var(--text-secondary)' }}>
            {chunk.content}
          </p>
        </div>
      ))}
    </div>
    </>
  )
}

// ── 文档行（含展开切块） ───────────────────────────────────────────────

function DocRow({
  doc,
  kbId,
  onDelete,
}: {
  doc: KBDocument
  kbId: string
  onDelete: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const canExpand = doc.status === 'completed'

  const handleRowClick = () => {
    if (canExpand) setExpanded(v => !v)
  }

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ backgroundColor: 'var(--bg-secondary)', borderColor: expanded ? 'var(--border-color)' : 'var(--border-subtle)' }}
    >
      {/* 主行 */}
      <div
        className={`group flex items-center gap-4 px-4 py-3 ${canExpand ? 'cursor-pointer' : ''}`}
        onClick={handleRowClick}
        onMouseEnter={e => { if (canExpand) (e.currentTarget as HTMLDivElement).style.backgroundColor = 'var(--hover-bg)' }}
        onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.backgroundColor = '' }}
      >
        {/* 展开箭头 */}
        <div className="w-4 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
          {canExpand
            ? (expanded
              ? <ChevronDown className="w-4 h-4" />
              : <ChevronRight className="w-4 h-4" />)
            : <div className="w-4" />
          }
        </div>

        {/* 文件图标 */}
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: 'var(--bg-tertiary)' }}
        >
          <FileText className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
        </div>

        {/* 文件信息 */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
            {doc.filename}
          </p>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-xs uppercase font-mono" style={{ color: 'var(--text-muted)' }}>
              {doc.file_type}
            </span>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {formatSize(doc.file_size)}
            </span>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {formatDate(doc.created_at)}
            </span>
            {canExpand && !expanded && (
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                点击查看切块
              </span>
            )}
          </div>
        </div>

        {/* 状态 */}
        <div className="flex-shrink-0" onClick={e => e.stopPropagation()}>
          <StatusBadge doc={doc} />
        </div>

        {/* 删除 */}
        {(doc.status === 'completed' || doc.status === 'failed') && (
          <button
            onClick={e => { e.stopPropagation(); onDelete() }}
            className="opacity-0 group-hover:opacity-100 p-1 rounded transition-all cursor-pointer flex-shrink-0"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={e => { e.currentTarget.style.color = '#ef4444' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* 切块面板 */}
      {expanded && (
        <div
          className="px-4 pb-4 border-t"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="pt-3 mb-1">
            <ChunkPanel kbId={kbId} docId={doc.id} chunkCount={doc.chunk_count} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── 工具函数 ──────────────────────────────────────────────────────────

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// ── 主页面 ────────────────────────────────────────────────────────────

export default function KnowledgeBaseDetailPage() {
  const { id: kbId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: kb, isLoading: kbLoading } = useQuery({
    queryKey: ['knowledge-base', kbId],
    queryFn: () => knowledgeBaseApi.get(kbId!),
    enabled: !!kbId,
  })

  const { data: docData, isLoading: docsLoading } = useQuery({
    queryKey: ['kb-documents', kbId],
    queryFn: () => knowledgeBaseApi.listDocuments(kbId!),
    enabled: !!kbId,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some(d => d.status === 'pending' || d.status === 'processing') ? 3000 : false
    },
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => knowledgeBaseApi.uploadDocument(kbId!, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-documents', kbId] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => knowledgeBaseApi.deleteDocument(kbId!, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-documents', kbId] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadMutation.mutate(file)
    e.target.value = ''
  }

  if (kbLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>
      </div>
    )
  }

  if (!kb) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>知识库不存在</p>
      </div>
    )
  }

  const docs = docData?.items ?? []

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/knowledge-bases')}
            className="p-1 rounded-md transition-colors cursor-pointer flex-shrink-0"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-tertiary)' }}
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-2 min-w-0">
            <Database className="w-4 h-4 flex-shrink-0" style={{ color: '#7c3aed' }} />
            <h1 className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{kb.name}</h1>
            {kb.description && (
              <span className="text-xs hidden sm:block" style={{ color: 'var(--text-muted)' }}>· {kb.description}</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {uploadMutation.isPending && (
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              上传中…
            </span>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white transition-colors cursor-pointer"
          >
            <Upload className="w-3.5 h-3.5" />
            上传文件
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.xlsx,.txt"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      </div>

      {/* Upload error */}
      {uploadMutation.isError && (
        <div className="mx-6 mt-3 px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: '#450a0a', color: '#fca5a5' }}>
          上传失败：{(uploadMutation.error as Error)?.message ?? '请重试'}
        </div>
      )}

      {/* Document list */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {docsLoading && (
          <div className="flex items-center justify-center py-20">
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>
          </div>
        )}

        {!docsLoading && docs.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center"
              style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
            >
              <FileText className="w-6 h-6" style={{ color: 'var(--text-tertiary)' }} />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>还没有文档</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                点击"上传文件"添加 PDF、Word、Excel 或 TXT 文档
              </p>
            </div>
          </div>
        )}

        {docs.length > 0 && (
          <div className="space-y-2">
            {docs.map(doc => (
              <DocRow
                key={doc.id}
                doc={doc}
                kbId={kbId!}
                onDelete={() => {
                  if (confirm(`确认删除文档「${doc.filename}」？`)) {
                    deleteMutation.mutate(doc.id)
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
