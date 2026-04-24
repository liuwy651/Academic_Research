import { MessageSquarePlus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { conversationsApi } from '../api/conversations'

export default function DashboardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: conversationsApi.create,
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/conversations/${conv.id}`)
    },
  })

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-5 text-center px-8">
      <div className="w-14 h-14 bg-white/[0.03] border border-white/[0.07] rounded-2xl
                      flex items-center justify-center">
        <MessageSquarePlus className="w-6 h-6 text-[#404040]" />
      </div>

      <div className="space-y-1.5">
        <p className="text-sm font-medium text-[#a3a3a3]">Start a conversation</p>
        <p className="text-xs text-[#3f3f3f] max-w-xs">
          Select an existing chat from the sidebar or create a new one to get started.
        </p>
      </div>

      <button
        onClick={() => createMutation.mutate('New Conversation')}
        disabled={createMutation.isPending}
        className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500
                   disabled:opacity-50 text-white text-xs font-medium rounded-lg
                   transition-colors cursor-pointer"
      >
        New Chat
      </button>
    </div>
  )
}
