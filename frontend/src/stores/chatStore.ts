import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { v4 as uuidv4 } from 'uuid'
import type { ChatMessage, TraceStep, Citation, TextDoc, CodeInterpreterDoc } from '@/types/chat'
import { getSavePreference, setSavePreference } from '@/services/conversations'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const sessionId = ref(uuidv4())
  const isStreaming = ref(false)
  const streamingStatus = ref('')
  const webSearchEnabled = ref(false)
  const searchModeLocked = ref(false)

  // Document upload state
  const textDocs = ref<TextDoc[]>([])
  const codeInterpreterDocs = ref<CodeInterpreterDoc[]>([])

  // Sources from the latest answer
  const citations = ref<Citation[]>([])

  // Whether the user has opted in to persisting their chats. Opt-in: defaults
  // to false until loaded from / set via the backend. Drives whether finished
  // conversations are saved for later continuation.
  const saveChatsEnabled = ref(false)

  const hasMessages = computed(() => messages.value.length > 0)

  function addMessage(message: ChatMessage) {
    messages.value.push(message)
  }

  function updateLastAssistantMessage(content: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = content
    }
  }

  function setTraceSteps(steps: TraceStep[]) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.traceSteps = steps
    }
  }

  function setCitations(cites: Citation[]) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.citations = cites
    }
    citations.value = cites
  }

  function clearChat() {
    messages.value = []
    citations.value = []
    webSearchEnabled.value = false
    searchModeLocked.value = false
    textDocs.value = []
    codeInterpreterDocs.value = []
    sessionId.value = uuidv4()
  }

  function lockSearchMode() {
    searchModeLocked.value = true
  }

  function setWebSearch(enabled: boolean) {
    webSearchEnabled.value = enabled
    if (enabled) {
      textDocs.value = []
      codeInterpreterDocs.value = []
    }
  }

  /** Load the save opt-in flag from the backend (best-effort). */
  async function loadSavePreference() {
    try {
      saveChatsEnabled.value = await getSavePreference()
    } catch {
      // Default to off if the preference can't be read.
      saveChatsEnabled.value = false
    }
  }

  /**
   * Persist the save opt-in flag. Updates local state optimistically and
   * reconciles with the stored value the backend returns.
   */
  async function updateSavePreference(enabled: boolean) {
    saveChatsEnabled.value = enabled
    try {
      saveChatsEnabled.value = await setSavePreference(enabled)
    } catch {
      // Revert on failure.
      saveChatsEnabled.value = !enabled
    }
  }

  return {
    messages,
    sessionId,
    isStreaming,
    streamingStatus,
    webSearchEnabled,
    searchModeLocked,
    textDocs,
    codeInterpreterDocs,
    citations,
    saveChatsEnabled,
    hasMessages,
    loadSavePreference,
    updateSavePreference,
    addMessage,
    updateLastAssistantMessage,
    setTraceSteps,
    setCitations,
    clearChat,
    lockSearchMode,
    setWebSearch,
  }
})
