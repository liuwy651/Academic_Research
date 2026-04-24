export type Message = {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  parent_id: string | null
  summary: string | null
  context_tokens: number | null
}

export type LocalMessage = Message & { streaming?: boolean }

export type TreeNode = {
  id: string
  parent_id: string | null
  role: 'user' | 'assistant' | 'system'
  summary: string | null
  children: TreeNode[]
}
