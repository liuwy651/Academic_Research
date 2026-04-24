import { create } from 'zustand'

type ConversationState = {
  activeId: string | null
  setActiveId: (id: string | null) => void
  activeNodeId: string | null
  setActiveNodeId: (id: string | null) => void
  isGenerating: boolean
  abortController: AbortController | null
  startGenerating: (controller: AbortController) => void
  stopGenerating: () => void
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  activeId: null,
  setActiveId: (id) => set({ activeId: id }),
  activeNodeId: null,
  setActiveNodeId: (id) => set({ activeNodeId: id }),
  isGenerating: false,
  abortController: null,
  startGenerating: (controller) => set({ isGenerating: true, abortController: controller }),
  stopGenerating: () => {
    get().abortController?.abort()
    set({ isGenerating: false, abortController: null })
  },
}))
