export interface KnowledgeBase {
  id: string
  name: string
  description: string | null
  document_count: number
  created_at: string
  updated_at: string
}

export interface KBDocument {
  id: string
  knowledge_base_id: string
  filename: string
  file_type: string
  file_size: number
  chunk_count: number | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseListOut {
  items: KnowledgeBase[]
  total: number
}

export interface DocumentListOut {
  items: KBDocument[]
  total: number
}
