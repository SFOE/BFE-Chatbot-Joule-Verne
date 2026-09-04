import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { v4 as uuidv4 } from 'uuid'
import type { ChatMessage, TraceStep, Citation, TextDoc, CodeInterpreterDoc } from '@/types/chat'

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

  // Document upload state
  const textDocs = ref<TextDoc[]>([])
  const codeInterpreterDocs = ref<CodeInterpreterDoc[]>([])

  // Sources from the latest answer
  const citations = ref<Citation[]>([])

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
    messages.value = []
    citations.value = []
    webSearchEnabled.value = false
    specificKbId.value = null
    customMode.value = false
    customTools.value = new Set()
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
      specificKbId.value = null
      customMode.value = false
      customTools.value = new Set()
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

  return {
    messages,
    sessionId,
    isStreaming,
    streamingStatus,
    webSearchEnabled,
    specificKbId,
    customMode,
    customTools,
    webSearchActive,
    uploadAllowed,
    searchModeLocked,
    textDocs,
    codeInterpreterDocs,
    citations,
    hasMessages,
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
  }
})
