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

  // Selected specific KB ID (null when using BFE-Wissen or Websuche)
  const specificKbId = ref<string | null>(null)

  // "Own choice" (custom) mode: the user picks an explicit set of tools.
  // When active, the request sends a `capabilities` payload composed from
  // exactly these selections — nothing implied. The agent gets only these.
  const customMode = ref(false)
  // Static capability keys the agent understands (must match the agent's
  // CAPABILITY_REGISTRY keys in agent-jouleverne/main.py).
  const customTools = ref<Set<string>>(new Set())
  // Specific Knowledge Base IDs selected in custom mode (validated agent-side).
  const customKbIds = ref<Set<string>>(new Set())

  // Document upload state
  const textDocs = ref<TextDoc[]>([])
  const codeInterpreterDocs = ref<CodeInterpreterDoc[]>([])
  // Large documents indexed server-side (RAG). Only a reference is held; the
  // agent searches them on demand. Shown so the user sees what was uploaded.
  const indexedDocs = ref<IndexedDoc[]>([])

  // Agent-facing metadata block for indexed ("teilweise") documents: name,
  // type, size and a short preview of each. Not shown in the UI; sent with the
  // chat request so the agent knows these documents exist and to search them.
  // Accumulated across upload batches (one block per upload that indexed docs).
  const documentSummary = ref('')

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

  // Whether web search is active for the current request. In custom mode this
  // depends on whether "web_search" is among the selected tools; otherwise it
  // is the classic web-search toggle. Upload is disabled whenever this is true.
  const webSearchActive = computed(() =>
    customMode.value ? customTools.value.has('web_search') : webSearchEnabled.value,
  )

  // Whether document upload is allowed. Blocked when web search is active (to
  // avoid sending uploaded content to an external web search service).
  const uploadAllowed = computed(() => !webSearchActive.value)

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
    specificKbId.value = null
    customMode.value = false
    customTools.value = new Set()
    customKbIds.value = new Set()
    searchModeLocked.value = false
    textDocs.value = []
    codeInterpreterDocs.value = []
    indexedDocs.value = []
    documentSummary.value = ''
    sessionId.value = uuidv4()
  }

  function lockSearchMode() {
    searchModeLocked.value = true
  }

  function setWebSearch(enabled: boolean) {
    webSearchEnabled.value = enabled
    if (enabled) {
      specificKbId.value = null
      customMode.value = false
      customTools.value = new Set()
      customKbIds.value = new Set()
      textDocs.value = []
      codeInterpreterDocs.value = []
    }
  }

  function setSpecificKb(kbId: string | null) {
    specificKbId.value = kbId
    if (kbId) {
      // Specific KB mode does not use web search or uploaded documents
      webSearchEnabled.value = false
      customMode.value = false
      customTools.value = new Set()
      customKbIds.value = new Set()
      textDocs.value = []
      codeInterpreterDocs.value = []
    }
  }

  /** Enter "own choice" mode with an initial (possibly empty) tool set. */
  function enableCustomMode() {
    customMode.value = true
    webSearchEnabled.value = false
    specificKbId.value = null
  }

  /** Leave custom mode, clearing the selected tools. */
  function disableCustomMode() {
    customMode.value = false
    customTools.value = new Set()
    customKbIds.value = new Set()
  }

  /** Toggle a specific Knowledge Base ID in the custom selection. */
  function toggleCustomKb(kbId: string) {
    const next = new Set(customKbIds.value)
    if (next.has(kbId)) {
      next.delete(kbId)
    } else {
      next.add(kbId)
    }
    customKbIds.value = next
  }

  /** Toggle a single tool in the custom selection. */
  function toggleCustomTool(tool: string) {
    const next = new Set(customTools.value)
    if (next.has(tool)) {
      next.delete(tool)
    } else {
      next.add(tool)
    }
    customTools.value = next
    // Enabling web search disables upload — clear any pending documents.
    if (tool === 'web_search' && next.has('web_search')) {
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
    // Previews are not persisted; a continued chat relies on the agent's
    // search tool knowing the indexed docs exist via the restored file list.
    documentSummary.value = ''
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
    specificKbId,
    customMode,
    customTools,
    customKbIds,
    webSearchActive,
    uploadAllowed,
    searchModeLocked,
    textDocs,
    codeInterpreterDocs,
    indexedDocs,
    documentSummary,
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
    setSpecificKb,
    enableCustomMode,
    disableCustomMode,
    toggleCustomTool,
    toggleCustomKb,
  }
})
