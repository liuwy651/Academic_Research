export type FileAttachmentInfo = {
  id: string
  original_filename: string
  file_type: string
  token_estimate: number | null
}

export type Message = {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  parent_id: string | null
  summary: string | null
  context_tokens: number | null
  files: FileAttachmentInfo[]
}

export type ToolStatus = {
  name: string
  args: Record<string, unknown>
}

export type LocalMessage = Message & {
  streaming?: boolean
  toolStatus?: ToolStatus
  images?: string[]
}

export type TreeNode = {
  id: string
  parent_id: string | null
  role: 'user' | 'assistant' | 'system'
  summary: string | null
  children: TreeNode[]
}
