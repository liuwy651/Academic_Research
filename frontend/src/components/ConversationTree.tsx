import { useQuery } from '@tanstack/react-query'
import { GitBranch } from 'lucide-react'
import { conversationsApi } from '../api/conversations'
import type { TreeNode } from '../types/message'

// ── Exchange node (one visual node = one Q&A turn) ─────────────────────────────

type Exchange = {
  userId: string
  assistantId: string | null   // null while still streaming
  summary: string | null       // from the user message
  parentUserId: string | null  // visual parent (the user msg of the prior exchange)
  children: Exchange[]
}

/**
 * Build a tree of exchanges from the flat message list.
 *
 * Data chain in DB:
 *   user1 (parent=null) → assistant1 (parent=user1)
 *   → user2 (parent=assistant1) → assistant2 (parent=user2)
 *
 * Visual parent of exchange(user2) = exchange(user1):
 *   user2.parent_id = assistant1.id
 *   assistant1.parent_id = user1.id  ← visual parent user
 */
function buildExchangeTree(flatNodes: TreeNode[]): Exchange[] {
  const byId = new Map<string, TreeNode>()
  for (const n of flatNodes) byId.set(n.id, n)

  // assistant reply lookup: userId → assistantId
  const assistantOf = new Map<string, string>()
  for (const n of flatNodes) {
    if (n.role === 'assistant' && n.parent_id) {
      assistantOf.set(n.parent_id, n.id)
    }
  }

  const exchanges = new Map<string, Exchange>()
  for (const n of flatNodes) {
    if (n.role !== 'user') continue

    // Compute visual parent:
    // - n.parent_id → assistant message
    // - that assistant's parent_id → previous user message
    let parentUserId: string | null = null
    if (n.parent_id) {
      const assistantMsg = byId.get(n.parent_id)
      if (assistantMsg?.parent_id) {
        parentUserId = assistantMsg.parent_id
      }
    }

    exchanges.set(n.id, {
      userId: n.id,
      assistantId: assistantOf.get(n.id) ?? null,
      summary: n.summary,
      parentUserId,
      children: [],
    })
  }

  const roots: Exchange[] = []
  for (const ex of exchanges.values()) {
    if (ex.parentUserId === null) {
      roots.push(ex)
    } else {
      exchanges.get(ex.parentUserId)?.children.push(ex)
    }
  }

  return roots
}

// ── Single exchange node ───────────────────────────────────────────────────────

type ExchangeItemProps = {
  exchange: Exchange
  activeNodeId: string | null
  onSelect: (id: string) => void
  depth: number
  isLast: boolean
}

function ExchangeItem({ exchange, activeNodeId, onSelect, depth, isLast }: ExchangeItemProps) {
  // Active when the current path ends at this exchange's user or assistant msg
  const isActive =
    activeNodeId === exchange.assistantId ||
    activeNodeId === exchange.userId

  const hasChildren = exchange.children.length > 0
  const label = exchange.summary?.trim() || '…'

  // Navigate to the end of this exchange (assistant reply if available)
  const handleClick = () => {
    onSelect(exchange.assistantId ?? exchange.userId)
  }

  return (
    <div className="relative">
      {/* vertical connector line from parent */}
      {depth > 0 && (
        <div
          className="absolute w-px bg-white/10"
          style={{
            left: depth * 18 - 9,
            top: 0,
            height: isLast ? '50%' : '100%',
          }}
        />
      )}

      {/* horizontal connector to node */}
      {depth > 0 && (
        <div
          className="absolute top-1/2 h-px bg-white/10"
          style={{ left: depth * 18 - 9, width: 9 }}
        />
      )}

      <div
        onClick={handleClick}
        className={`relative flex items-center gap-2 rounded cursor-pointer transition-colors text-xs select-none
          ${isActive
            ? 'bg-violet-600/20 text-violet-300'
            : 'text-white/50 hover:text-white/80 hover:bg-white/[0.04]'
          }`}
        style={{ paddingLeft: depth * 18 + 8, paddingTop: 6, paddingBottom: 6, paddingRight: 8 }}
      >
        {/* dot */}
        <span
          className={`flex-shrink-0 w-1.5 h-1.5 rounded-full transition-colors ${
            isActive ? 'bg-violet-400' : 'bg-white/20'
          }`}
        />

        <span className="truncate">{label}</span>

        {/* branch count badge */}
        {exchange.children.length > 1 && (
          <span className="ml-auto flex-shrink-0 px-1 py-0.5 rounded text-[9px] font-mono
                           bg-white/[0.06] text-white/30">
            {exchange.children.length}
          </span>
        )}

        {/* pending indicator (no assistant reply yet) */}
        {!exchange.assistantId && (
          <span className="ml-auto flex-shrink-0 w-1 h-1 rounded-full bg-amber-400/60 animate-pulse" />
        )}
      </div>

      {/* children */}
      {hasChildren && (
        <div className="relative">
          {/* vertical spine covering all siblings */}
          {exchange.children.length > 1 && (
            <div
              className="absolute w-px bg-white/10"
              style={{
                left: (depth + 1) * 18 - 9,
                top: 0,
                bottom: 0,
              }}
            />
          )}
          {exchange.children.map((child, i) => (
            <ExchangeItem
              key={child.userId}
              exchange={child}
              activeNodeId={activeNodeId}
              onSelect={onSelect}
              depth={depth + 1}
              isLast={i === exchange.children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── ConversationTree ───────────────────────────────────────────────────────────

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

  const roots = buildExchangeTree(flatNodes)

  return (
    <div className="flex flex-col h-full">
      {/* header */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-white/[0.06]">
        <GitBranch className="w-3.5 h-3.5 text-white/30" />
        <span className="text-xs text-white/40 font-medium tracking-wide uppercase">对话树</span>
        {roots.length > 0 && (
          <span className="ml-auto text-[10px] text-white/20 font-mono">{roots.length === 1 ? flatNodes.filter(n => n.role === 'user').length + ' 轮' : roots.length + ' 根'}</span>
        )}
      </div>

      {/* tree body */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading ? (
          <div className="flex items-center justify-center h-16">
            <div className="w-4 h-4 rounded-full border border-white/10 border-t-violet-400 animate-spin" />
          </div>
        ) : roots.length === 0 ? (
          <p className="text-center text-white/20 text-xs py-8">暂无对话</p>
        ) : (
          roots.map((root, i) => (
            <ExchangeItem
              key={root.userId}
              exchange={root}
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
