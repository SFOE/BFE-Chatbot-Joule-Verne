import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { v4 as uuidv4 } from 'uuid'
import type { ChatMessage, TraceStep, Citation, TextDoc, CodeInterpreterDoc, IndexedDoc } from '@/types/chat'
import {
  getSavePreference,
  setSavePreference,
  saveConversation,
  loadConversation,
  deleteEphemeralSession,
  listSessionFiles,
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
  // Large documents indexed server-side (RAG). Only a reference is held; the
  // agent searches them on demand. Shown so the user sees what was uploaded.
  const indexedDocs = ref<IndexedDoc[]>([])

  // True while an upload (incl. server-side indexing) is in progress. Blocks
  // sending so the user can't ask about a document before its index exists.
  const isUploading = ref(false)

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
    // When saving is off, the outgoing session's transcript lives in the
    // short-lived ephemeral store. Delete it right away rather than waiting for
    // the 1-day backstop. Best-effort; the lifecycle rule guarantees cleanup.
    if (!saveChatsEnabled.value && messages.value.length > 0) {
      const outgoing = sessionId.value
      void deleteEphemeralSession(outgoing).catch(() => {})
    }
    messages.value = []
    citations.value = []
    webSearchEnabled.value = false
    searchModeLocked.value = false
    textDocs.value = []
    codeInterpreterDocs.value = []
    indexedDocs.value = []
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
    indexedDocs.value = []
    applyModeConfig(detail.mode_config)
    if (messages.value.length > 0) {
      searchModeLocked.value = true
    }
    // Restore uploaded files so the UI reflects what the agent can still use in
    // this continued session (best-effort). CI files come back as references
    // (file_id, no bytes) — the agent loads them from S3 on demand.
    try {
      const sessionFiles = await listSessionFiles(detail.session_id)
      indexedDocs.value = sessionFiles
        .filter((f) => f.routing === 'index')
        .map((f) => ({ name: f.name, doc_id: f.doc_id ?? '', chunk_count: 0, file_id: f.file_id }))
      codeInterpreterDocs.value = sessionFiles
        .filter((f) => f.routing === 'ci')
        .map((f) => ({ name: f.name, media_type: f.media_type, file_id: f.file_id }))
    } catch {
      indexedDocs.value = []
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
    indexedDocs,
    isUploading,
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
