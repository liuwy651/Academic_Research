import { create } from 'zustand'

type ConversationState = {
  activeId: string | null
  setActiveId: (id: string | null) => void
}

export const useConversationStore = create<ConversationState>((set) => ({
  activeId: null,
  setActiveId: (id) => set({ activeId: id }),
}))
