import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Database, FileText, Plus, Trash2 } from 'lucide-react'
import { knowledgeBaseApi } from '../api/knowledgeBase'

export default function KnowledgeBasePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: knowledgeBaseApi.list,
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => knowledgeBaseApi.create(name),
    onSuccess: (kb) => {
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      setCreating(false)
      setNewName('')
      navigate(`/knowledge-bases/${kb.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: knowledgeBaseApi.deleteKb,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] }),
  })

  const handleCreate = () => {
    const name = newName.trim()
    if (!name) return
    createMutation.mutate(name)
  }

  const handleStartCreating = () => {
    setCreating(true)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-center gap-2.5">
          <Database className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
          <h1 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Knowledge Bases</h1>
          {data && (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}>
              {data.total}
            </span>
          )}
        </div>

        <button
          onClick={handleStartCreating}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer"
          style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
          onMouseEnter={e => {
            e.currentTarget.style.backgroundColor = 'var(--hover-bg)'
            e.currentTarget.style.color = 'var(--text-primary)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          <Plus className="w-3.5 h-3.5" />
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {/* Create form */}
        {creating && (
          <div
            className="mb-4 p-4 rounded-xl border"
            style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
          >
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>知识库名称</p>
            <div className="flex gap-2">
              <input
                ref={inputRef}
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleCreate()
                  if (e.key === 'Escape') { setCreating(false); setNewName('') }
                }}
                placeholder="e.g. 项目文档、法律手册..."
                className="flex-1 text-xs px-3 py-2 rounded-lg outline-none"
                style={{
                  backgroundColor: 'var(--bg-tertiary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-subtle)',
                }}
              />
              <button
                onClick={handleCreate}
                disabled={!newName.trim() || createMutation.isPending}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white transition-colors cursor-pointer"
              >
                {createMutation.isPending ? '创建中…' : '创建'}
              </button>
              <button
                onClick={() => { setCreating(false); setNewName('') }}
                className="px-3 py-2 text-xs rounded-lg transition-colors cursor-pointer"
                style={{ color: 'var(--text-muted)', backgroundColor: 'var(--bg-tertiary)' }}
              >
                取消
              </button>
            </div>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && data?.items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center"
              style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
            >
              <BookOpen className="w-6 h-6" style={{ color: 'var(--text-tertiary)' }} />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>还没有知识库</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>点击右上角"New"创建第一个知识库</p>
            </div>
          </div>
        )}

        {/* KB grid */}
        {data && data.items.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map(kb => (
              <div
                key={kb.id}
                className="group relative rounded-xl p-4 border cursor-pointer transition-all"
                style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)' }}
                onClick={() => navigate(`/knowledge-bases/${kb.id}`)}
                onMouseEnter={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = 'var(--border-color)'
                  el.style.backgroundColor = 'var(--hover-bg)'
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = 'var(--border-subtle)'
                  el.style.backgroundColor = 'var(--bg-secondary)'
                }}
              >
                {/* Delete button */}
                <button
                  onClick={e => {
                    e.stopPropagation()
                    if (confirm(`确认删除知识库「${kb.name}」及其所有文档？`)) {
                      deleteMutation.mutate(kb.id)
                    }
                  }}
                  className="absolute top-3 right-3 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={e => { e.currentTarget.style.color = '#ef4444' }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>

                <div className="flex items-start gap-3 mb-3">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: 'var(--bg-tertiary)' }}
                  >
                    <Database className="w-4 h-4" style={{ color: '#7c3aed' }} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{kb.name}</p>
                    {kb.description && (
                      <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>{kb.description}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                  <span className="flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {kb.document_count} 个文档
                  </span>
                  <span>{formatDate(kb.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
