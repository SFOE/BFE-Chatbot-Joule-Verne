import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { v4 as uuidv4 } from 'uuid'
import type { ChatMessage, TraceStep, Citation, TextDoc, CodeInterpreterDoc } from '@/types/chat'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const sessionId = ref(uuidv4())
  const isStreaming = ref(false)
  const webSearchEnabled = ref(false)
  const searchModeLocked = ref(false)

  // Document upload state
  const textDocs = ref<TextDoc[]>([])
  const codeInterpreterDocs = ref<CodeInterpreterDoc[]>([])

  // Sources from the latest answer
  const citations = ref<Citation[]>([])

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

  return {
    messages,
    sessionId,
    isStreaming,
    webSearchEnabled,
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
  }
})
