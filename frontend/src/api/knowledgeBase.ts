import client from './client'
import type { KnowledgeBase, KnowledgeBaseListOut, KBDocument, DocumentListOut } from '../types/knowledgeBase'

export const knowledgeBaseApi = {
  list: () =>
    client.get<KnowledgeBaseListOut>('/knowledge-bases').then(r => r.data),

  get: (id: string) =>
    client.get<KnowledgeBase>(`/knowledge-bases/${id}`).then(r => r.data),

  create: (name: string, description?: string) =>
    client.post<KnowledgeBase>('/knowledge-bases', { name, description }).then(r => r.data),

  update: (id: string, data: { name?: string; description?: string }) =>
    client.patch<KnowledgeBase>(`/knowledge-bases/${id}`, data).then(r => r.data),

  deleteKb: (id: string) =>
    client.delete(`/knowledge-bases/${id}`),

  listDocuments: (kbId: string) =>
    client.get<DocumentListOut>(`/knowledge-bases/${kbId}/documents`).then(r => r.data),

  getDocument: (kbId: string, docId: string) =>
    client.get<KBDocument>(`/knowledge-bases/${kbId}/documents/${docId}`).then(r => r.data),

  uploadDocument: (kbId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<KBDocument>(`/knowledge-bases/${kbId}/documents`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then(r => r.data)
  },

  deleteDocument: (kbId: string, docId: string) =>
    client.delete(`/knowledge-bases/${kbId}/documents/${docId}`),

  getChunks: (kbId: string, docId: string) =>
    client
      .get<{ total: number; chunks: { index: number; content: string }[]; level: 'parent' | 'child' }>(
        `/knowledge-bases/${kbId}/documents/${docId}/chunks`
      )
      .then(r => r.data),
}
