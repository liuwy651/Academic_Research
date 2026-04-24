export type Conversation = {
  id: string
  user_id: string
  title: string
  created_at: string
  updated_at: string
}

export type ConversationListResponse = {
  items: Conversation[]
  total: number
}
