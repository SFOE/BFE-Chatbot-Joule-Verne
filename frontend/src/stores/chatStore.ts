import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { v4 as uuidv4 } from 'uuid'
import type { ChatMessage, TraceStep, Citation, TextDoc, CodeInterpreterDoc } from '@/types/chat'
import {
  getSavePreference,
  setSavePreference,
  saveConversation,
  loadConversation,
  type ModeConfig,
} from '@/services/conversations'

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

  /** Snapshot the current tool/mode selection for persistence. */
  function currentModeConfig(): ModeConfig {
    return {
      customMode: customMode.value,
      customTools: Array.from(customTools.value),
      customKbIds: Array.from(customKbIds.value),
      webSearchEnabled: webSearchEnabled.value,
      specificKbId: specificKbId.value,
    }
  }

  /** Restore a persisted tool/mode selection into the store. */
  function applyModeConfig(config: ModeConfig | null) {
    if (!config) return
    customMode.value = config.customMode
    customTools.value = new Set(config.customTools)
    customKbIds.value = new Set(config.customKbIds)
    webSearchEnabled.value = config.webSearchEnabled
    specificKbId.value = config.specificKbId
  }

  /**
   * Persist the current conversation (best-effort). No-op when the user has
   * not opted in or there is nothing to save. Called after each answer.
   */
  async function persistConversation() {
    if (!saveChatsEnabled.value || messages.value.length === 0) return
    try {
      await saveConversation(sessionId.value, messages.value, currentModeConfig())
    } catch {
      // Best-effort — a failed save must never disrupt the chat.
    }
  }

  /**
   * Load a stored conversation into the store so the UI can continue it. Sets
   * the session id, restores the transcript and the saved mode config, and
   * locks the search mode (as it is after the first message of any chat).
   */
  async function openConversation(id: string) {
    const detail = await loadConversation(id)
    sessionId.value = detail.session_id
    messages.value = detail.messages
    citations.value = []
    textDocs.value = []
    codeInterpreterDocs.value = []
    applyModeConfig(detail.mode_config)
    if (messages.value.length > 0) {
      searchModeLocked.value = true
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
    persistConversation,
    openConversation,
    addMessage,
    updateLastAssistantMessage,
    setTraceSteps,
    setCitations,
    clearChat,
    lockSearchMode,
    setWebSearch,
  }
})
