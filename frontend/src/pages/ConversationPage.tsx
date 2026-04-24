import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare } from 'lucide-react'
import { conversationsApi } from '../api/conversations'

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>()

  const { data: conv } = useQuery({
    queryKey: ['conversations', id],
    queryFn: () => conversationsApi.get(id!),
    enabled: !!id,
  })

  return (
    <div className="flex-1 flex flex-col">
      {/* Header bar */}
      <div className="flex items-center px-5 py-3.5 border-b border-white/[0.06] bg-[#0e0e0e]">
        <MessageSquare className="w-4 h-4 text-[#525252] mr-2.5" />
        <span className="text-sm font-medium text-[#d4d4d4] truncate">
          {conv?.title ?? '…'}
        </span>
      </div>

      {/* Empty state placeholder — replaced by chat in S3 */}
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-8">
        <div className="w-12 h-12 bg-white/[0.03] border border-white/[0.06] rounded-xl
                        flex items-center justify-center">
          <MessageSquare className="w-5 h-5 text-[#303030]" />
        </div>
        <div className="space-y-1">
          <p className="text-sm text-[#525252]">Chat interface coming in S3</p>
          <p className="text-[10px] text-[#2f2f2f] font-mono">{id}</p>
        </div>
      </div>
    </div>
  )
}
