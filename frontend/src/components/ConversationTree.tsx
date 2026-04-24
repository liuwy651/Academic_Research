import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GitBranch, X } from 'lucide-react'
import { conversationsApi } from '../api/conversations'
import type { TreeNode } from '../types/message'

// ── Exchange (one Q&A turn = one visual node) ──────────────────────────────────

type Exchange = {
  userId: string
  assistantId: string | null
  summary: string | null
  parentUserId: string | null
  children: Exchange[]
}

function buildExchangeTree(flatNodes: TreeNode[]): Exchange[] {
  const byId = new Map<string, TreeNode>()
  for (const n of flatNodes) byId.set(n.id, n)

  const assistantOf = new Map<string, string>()
  for (const n of flatNodes) {
    if (n.role === 'assistant' && n.parent_id) assistantOf.set(n.parent_id, n.id)
  }

  const exchanges = new Map<string, Exchange>()
  for (const n of flatNodes) {
    if (n.role !== 'user') continue
    let parentUserId: string | null = null
    if (n.parent_id) {
      const assistant = byId.get(n.parent_id)
      if (assistant?.parent_id) parentUserId = assistant.parent_id
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
    if (ex.parentUserId === null) roots.push(ex)
    else exchanges.get(ex.parentUserId)?.children.push(ex)
  }
  return roots
}

// ── Top-down layout ────────────────────────────────────────────────────────────

const NW = 90, NH = 32, HG = 26, VG = 62, PAD = 20

type Pos = { x: number; y: number; cx: number }

function subtreeWidth(node: Exchange, cache: Map<string, number>): number {
  if (!node.children.length) { cache.set(node.userId, NW); return NW }
  let total = -HG
  for (const c of node.children) total += subtreeWidth(c, cache) + HG
  const w = Math.max(NW, total)
  cache.set(node.userId, w)
  return w
}

function placeNodes(
  node: Exchange, cx: number, y: number,
  cache: Map<string, number>,
  pos: Map<string, Pos>,
  depth: Map<string, number>,
  d: number,
) {
  pos.set(node.userId, { x: cx - NW / 2, y, cx })
  depth.set(node.userId, d)
  if (!node.children.length) return
  let total = -HG
  for (const c of node.children) total += cache.get(c.userId)! + HG
  let childX = cx - Math.max(NW, total) / 2
  for (const c of node.children) {
    const w = cache.get(c.userId)!
    placeNodes(c, childX + w / 2, y + NH + VG, cache, pos, depth, d + 1)
    childX += w + HG
  }
}

function layout(roots: Exchange[]) {
  const pos = new Map<string, Pos>()
  const depth = new Map<string, number>()
  const cache = new Map<string, number>()
  const flat: Exchange[] = []
  const walk = (n: Exchange) => { flat.push(n); n.children.forEach(walk) }

  if (!roots.length) return { pos, depth, svgW: 0, svgH: 0, flat }

  for (const r of roots) subtreeWidth(r, cache)

  let rx = PAD
  for (const r of roots) {
    const w = cache.get(r.userId)!
    placeNodes(r, rx + w / 2, PAD, cache, pos, depth, 0)
    walk(r)
    rx += w + HG
  }

  let maxX = 0, maxY = 0
  for (const p of pos.values()) { maxX = Math.max(maxX, p.x + NW); maxY = Math.max(maxY, p.y + NH) }
  return { pos, depth, svgW: maxX + PAD, svgH: maxY + PAD, flat }
}

// Node color by depth
function nodeStyle(d: number, active: boolean) {
  if (active) return { fill: '#4c1d95', stroke: '#7c3aed', text: '#ede9fe' }
  if (d === 0) return { fill: '#3b1515', stroke: '#7a3030', text: '#fde8e8' }
  if (d === 1) return { fill: '#14322a', stroke: '#2d6b50', text: '#d1fae5' }
  return { fill: '#d9e84a', stroke: '#a8bc2a', text: '#1a1800' }
}

// ── Floating draggable panel ───────────────────────────────────────────────────

type Props = {
  convId: string
  activeNodeId: string | null
  onSelectNode: (id: string) => void
  onClose: () => void
}

export default function ConversationTree({ convId, activeNodeId, onSelectNode, onClose }: Props) {
  const [panelPos, setPanelPos] = useState({ x: Math.max(0, window.innerWidth - 440), y: 80 })
  const [panelSize, setPanelSize] = useState({ w: 400, h: 460 })

  const { data: flatNodes = [], isLoading } = useQuery({
    queryKey: ['tree', convId],
    queryFn: () => conversationsApi.getTree(convId),
    staleTime: 0,
  })

  const roots = buildExchangeTree(flatNodes)
  const { pos, depth, svgW, svgH, flat } = layout(roots)

  // Drag title bar
  const onDragDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) return
    e.preventDefault()
    const sx = e.clientX, sy = e.clientY, ox = panelPos.x, oy = panelPos.y
    const onMove = (ev: MouseEvent) =>
      setPanelPos({ x: Math.max(0, ox + ev.clientX - sx), y: Math.max(0, oy + ev.clientY - sy) })
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  // Resize bottom-right corner
  const onResizeDown = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const sx = e.clientX, sy = e.clientY, ow = panelSize.w, oh = panelSize.h
    const onMove = (ev: MouseEvent) =>
      setPanelSize({ w: Math.max(280, ow + ev.clientX - sx), h: Math.max(180, oh + ev.clientY - sy) })
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  return (
    <div
      style={{ position: 'fixed', left: panelPos.x, top: panelPos.y, width: panelSize.w, height: panelSize.h, zIndex: 50 }}
      className="flex flex-col rounded-xl border border-white/[0.12] bg-[#0b0b0b]/95 shadow-[0_8px_40px_rgba(0,0,0,0.7)] backdrop-blur-sm overflow-hidden"
    >
      {/* Title bar */}
      <div
        onMouseDown={onDragDown}
        className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.06] cursor-grab active:cursor-grabbing select-none flex-shrink-0"
      >
        <GitBranch className="w-3.5 h-3.5 text-violet-400/60" />
        <span className="flex-1 text-[11px] font-medium text-white/40 uppercase tracking-widest">对话树</span>
        {flat.length > 0 && (
          <span className="text-[10px] text-white/20 font-mono mr-1">{flat.length} 轮</span>
        )}
        <button
          onClick={onClose}
          className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/[0.08] text-white/25 hover:text-white/60 transition-colors cursor-pointer"
        >
          <X className="w-3 h-3" />
        </button>
      </div>

      {/* SVG tree canvas */}
      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-5 h-5 rounded-full border border-white/10 border-t-violet-500 animate-spin" />
          </div>
        ) : flat.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <GitBranch className="w-8 h-8 text-white/10" />
            <p className="text-xs text-white/20">暂无对话</p>
          </div>
        ) : (
          <svg width={svgW} height={svgH} style={{ display: 'block', minWidth: '100%', minHeight: '100%' }}>
            <defs>
              <marker id="arr" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#505050" />
              </marker>
            </defs>

            {/* Curved edges */}
            {flat.map(ex => {
              const pp = pos.get(ex.userId)
              if (!pp) return null
              return ex.children.map(child => {
                const cp = pos.get(child.userId)
                if (!cp) return null
                const y1 = pp.y + NH, y2 = cp.y, my = (y1 + y2) / 2
                return (
                  <path
                    key={`${ex.userId}-${child.userId}`}
                    d={`M ${pp.cx} ${y1} C ${pp.cx} ${my} ${cp.cx} ${my} ${cp.cx} ${y2}`}
                    fill="none" stroke="#3a3a3a" strokeWidth={1.5}
                    markerEnd="url(#arr)"
                  />
                )
              })
            })}

            {/* Nodes */}
            {flat.map(ex => {
              const p = pos.get(ex.userId)
              if (!p) return null
              const d = depth.get(ex.userId) ?? 0
              const isActive = activeNodeId === ex.assistantId || activeNodeId === ex.userId
              const { fill, stroke, text } = nodeStyle(d, isActive)
              const label = (ex.summary?.trim() || '…').slice(0, 9)
              return (
                <g key={ex.userId} onClick={() => onSelectNode(ex.assistantId ?? ex.userId)} style={{ cursor: 'pointer' }}>
                  {isActive && (
                    <rect x={p.x - 3} y={p.y - 3} width={NW + 6} height={NH + 6} rx={9}
                      fill="none" stroke="#7c3aed" strokeWidth={1} opacity={0.45} />
                  )}
                  <rect x={p.x} y={p.y} width={NW} height={NH} rx={6} fill={fill} stroke={stroke} strokeWidth={1.5} />
                  <text
                    x={p.cx} y={p.y + NH / 2} textAnchor="middle" dominantBaseline="middle"
                    fill={text} fontSize={10.5}
                    fontFamily="-apple-system, system-ui, sans-serif"
                    fontWeight={isActive ? '600' : '400'}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {label}
                  </text>
                  {!ex.assistantId && (
                    <circle cx={p.x + NW - 7} cy={p.y + 7} r={3} fill="#f59e0b" opacity={0.85} />
                  )}
                </g>
              )
            })}
          </svg>
        )}
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={onResizeDown}
        style={{ position: 'absolute', bottom: 0, right: 0, width: 18, height: 18, cursor: 'nwse-resize' }}
        className="flex items-end justify-end p-1.5"
      >
        <svg width="9" height="9" viewBox="0 0 9 9">
          <line x1="2" y1="8" x2="8" y2="2" stroke="#3a3a3a" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="5" y1="8" x2="8" y2="5" stroke="#3a3a3a" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </div>
    </div>
  )
}
