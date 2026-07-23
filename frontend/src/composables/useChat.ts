import { useChatStore } from '@/stores/chatStore'
import type { TraceStep, Citation } from '@/types/chat'

/**
 * Composable that handles sending a message and streaming the SSE response.
 */
export function useChat() {
  const store = useChatStore()

  async function sendMessage(message: string) {
    if (!message.trim() || store.isStreaming) return

    // Add user message
    store.addMessage({ role: 'user', content: message })

    // Lock search mode after first message
    if (!store.searchModeLocked) {
      store.lockSearchMode()
    }

    // Prepare assistant placeholder
    store.addMessage({ role: 'assistant', content: '', traceSteps: [], citations: [] })
    store.isStreaming = true

    const traceSteps: TraceStep[] = []
    const citations: Citation[] = []
    let fullText = ''

    // Build session attributes from uploaded docs
    const sessionAttributes: Record<string, string> | undefined =
      store.textDocs.length > 0
        ? {
            uploaded_document: store.textDocs.map((d) => d.context).join('\n\n---\n\n'),
            document_name: store.textDocs.map((d) => d.name).join(', '),
            context_mode: store.textDocs.length > 1 ? 'multi' : store.textDocs[0].context_mode,
          }
        : undefined

    try {
      const response = await fetch('/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: store.sessionId,
          web_search: store.webSearchEnabled,
          session_attributes: sessionAttributes,
        }),
      })

      if (!response.ok || !response.body) {
        store.updateLastAssistantMessage('Fehler bei der Kommunikation mit dem Server.')
        store.isStreaming = false
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE lines
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6)
            handleEvent(eventType, data, traceSteps, citations, (text) => {
              fullText += text
              store.updateLastAssistantMessage(fullText)
            })
          }
        }
      }

      store.setTraceSteps(traceSteps)
      store.setCitations(citations)
    } catch (error) {
      store.updateLastAssistantMessage('Verbindungsfehler. Bitte versuchen Sie es erneut.')
    } finally {
      store.isStreaming = false
    }
  }

  return { sendMessage }
}

function handleEvent(
  eventType: string,
  data: string,
  traceSteps: TraceStep[],
  citations: Citation[],
  onToken: (text: string) => void,
) {
  try {
    const parsed = JSON.parse(data)

    switch (eventType) {
      case 'token':
        onToken(parsed.text)
        break
      case 'trace':
        traceSteps.push({ label: parsed.label, detail: parsed.detail })
        break
      case 'citation':
        citations.push({ source: parsed.source, text: parsed.text })
        break
      case 'error':
        onToken(`\n\n⚠️ ${parsed.detail || 'Ein Fehler ist aufgetreten.'}`)
        break
      case 'done':
        break
    }
  } catch {
    // Skip malformed events
  }
}
