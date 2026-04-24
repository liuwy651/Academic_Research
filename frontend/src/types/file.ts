export type FileResponse = {
  id: string
  conversation_id: string
  message_id: string | null
  original_filename: string
  file_type: 'pdf' | 'markdown'
  file_size: number
  token_estimate: number | null
  created_at: string
}

// Local state while the file is being uploaded
export type PendingFile = {
  localId: string          // temporary client-side id
  file: File               // browser File object
  status: 'uploading' | 'done' | 'error'
  fileResponse?: FileResponse
  error?: string
}
