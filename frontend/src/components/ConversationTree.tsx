import { useQuery } from '@tanstack/react-query'
import { GitBranch } from 'lucide-react'
import { conversationsApi } from '../api/conversations'
import type { TreeNode } from '../types/message'

function buildTree(flatNodes: Omit<TreeNode, 'children'>[]): TreeNode[] {
  const map = new Map<string, TreeNode>()
  for (const n of flatNodes) map.set(n.id, { ...n, children: [] })

  const roots: TreeNode[] = []
  for (const n of flatNodes) {
    const node = map.get(n.id)!
    if (n.parent_id === null) {
      roots.push(node)
    } else {
      map.get(n.parent_id)?.children.push(node)
    }
  }
  return roots
}

type NodeItemProps = {
  node: TreeNode
  activeNodeId: string | null
  onSelect: (id: string) => void
  depth: number
  isLast: boolean
}

function NodeItem({ node, activeNodeId, onSelect, depth, isLast }: NodeItemProps) {
  const isActive = node.id === activeNodeId
  const hasChildren = node.children.length > 0
  const label = node.summary?.trim() || (node.role === 'user' ? '(空)' : '…')

  return (
    <div className="relative">
      {/* vertical connector line from parent */}
      {depth > 0 && (
        <div
          className="absolute left-0 top-0 w-px bg-white/10"
          style={{ height: isLast ? '50%' : '100%', left: depth * 16 - 8 }}
        />
      )}

      {/* horizontal connector line */}
      {depth > 0 && (
        <div
          className="absolute top-1/2 h-px bg-white/10"
          style={{ left: depth * 16 - 8, width: 8 }}
        />
      )}

      <div
        onClick={() => onSelect(node.id)}
        className={`relative flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors text-xs
          ${isActive
            ? 'bg-violet-600/25 text-violet-300'
            : 'text-white/50 hover:text-white/80 hover:bg-white/[0.04]'
          }`}
        style={{ paddingLeft: depth * 16 + 8 }}
      >
        {/* role dot */}
        <span
          className={`flex-shrink-0 w-1.5 h-1.5 rounded-full ${
            node.role === 'user' ? 'bg-violet-400' : 'bg-emerald-400'
          }`}
        />

        <span className="truncate max-w-[120px]">{label}</span>

        {hasChildren && node.children.length > 1 && (
          <span className="ml-auto flex-shrink-0 text-[10px] text-white/30 font-mono">
            {node.children.length}
          </span>
        )}
      </div>

      {/* children */}
      {hasChildren && (
        <div className="relative">
          {/* full-height vertical line for non-last children */}
          {node.children.length > 1 && (
            <div
              className="absolute w-px bg-white/10"
              style={{
                left: (depth + 1) * 16 - 8,
                top: 0,
                bottom: 0,
              }}
            />
          )}
          {node.children.map((child, i) => (
            <NodeItem
              key={child.id}
              node={child}
              activeNodeId={activeNodeId}
              onSelect={onSelect}
              depth={depth + 1}
              isLast={i === node.children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

type Props = {
  convId: string
  activeNodeId: string | null
  onSelectNode: (id: string) => void
}

export default function ConversationTree({ convId, activeNodeId, onSelectNode }: Props) {
  const { data: flatNodes = [], isLoading } = useQuery({
    queryKey: ['tree', convId],
    queryFn: () => conversationsApi.getTree(convId),
    staleTime: 0,
  })

  const roots = buildTree(flatNodes)

  return (
    <div className="flex flex-col h-full">
      {/* header */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-white/[0.06]">
        <GitBranch className="w-3.5 h-3.5 text-white/30" />
        <span className="text-xs text-white/40 font-medium tracking-wide uppercase">对话树</span>
      </div>

      {/* tree body */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {isLoading ? (
          <div className="flex items-center justify-center h-16">
            <div className="w-4 h-4 rounded-full border border-white/10 border-t-violet-400 animate-spin" />
          </div>
        ) : roots.length === 0 ? (
          <p className="text-center text-white/20 text-xs py-8">暂无消息</p>
        ) : (
          roots.map((root, i) => (
            <NodeItem
              key={root.id}
              node={root}
              activeNodeId={activeNodeId}
              onSelect={onSelectNode}
              depth={0}
              isLast={i === roots.length - 1}
            />
          ))
        )}
      </div>
    </div>
  )
}
