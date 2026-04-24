import client from './client'
import type { Conversation, ConversationListResponse } from '../types/conversation'
import type { Message, TreeNode } from '../types/message'

export const conversationsApi = {
  list: (limit = 50) =>
    client.get<ConversationListResponse>('/conversations', { params: { limit } }).then(r => r.data),

  get: (id: string) =>
    client.get<Conversation>(`/conversations/${id}`).then(r => r.data),

  create: (title = 'New Conversation') =>
    client.post<Conversation>('/conversations', { title }).then(r => r.data),

  update: (id: string, title: string) =>
    client.patch<Conversation>(`/conversations/${id}`, { title }).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/conversations/${id}`),

  getMessages: (id: string, nodeId?: string) =>
    client
      .get<Message[]>(`/conversations/${id}/messages`, {
        params: nodeId ? { node_id: nodeId } : undefined,
      })
      .then(r => r.data),

  getTree: (id: string) =>
    client.get<TreeNode[]>(`/conversations/${id}/tree`).then(r => r.data),
}
