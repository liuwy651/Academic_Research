import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { conversationsApi } from '../api/conversations'

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>()

  const { data: conv } = useQuery({
    queryKey: ['conversations', id],
    queryFn: () => conversationsApi.get(id!),
    enabled: !!id,
  })

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      flexDirection: 'column',
      gap: '0.5rem',
      color: '#555',
    }}>
      <p style={{ fontSize: '1rem', color: '#888' }}>{conv?.title ?? '…'}</p>
      <p style={{ fontSize: '0.8rem' }}>Chat interface coming in S3</p>
      <p style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#444' }}>{id}</p>
    </div>
  )
}
