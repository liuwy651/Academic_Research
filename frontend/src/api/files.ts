import client from './client'
import type { FileResponse } from '../types/file'

export const filesApi = {
  upload: (convId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<FileResponse>(`/conversations/${convId}/files`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then(r => r.data)
  },

  list: (convId: string) =>
    client.get<FileResponse[]>(`/conversations/${convId}/files`).then(r => r.data),

  delete: (convId: string, fileId: string) =>
    client.delete(`/conversations/${convId}/files/${fileId}`),
}
