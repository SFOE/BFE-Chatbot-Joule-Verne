import { useChatStore } from '@/stores/chatStore'
import { backendHttp } from '@/services/http'
import type { TraceStep, Citation, FeedbackPayload } from '@/types/chat'
import i18n from '@/i18n'

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
      store.textDocs.length > 0 || store.codeInterpreterDocs.length > 0
        ? {
            uploaded_document: store.textDocs.length > 0
              ? store.textDocs.map((d) => d.context).join('\n\n---\n\n')
              : '[Documents sent to Code Interpreter for analysis]',
            document_name: [
              ...store.textDocs.map((d) => d.name),
              ...store.codeInterpreterDocs.map((d) => d.name),
            ].join(', '),
            context_mode: store.codeInterpreterDocs.length > 0 && store.textDocs.length === 0
              ? 'code_interpreter'
              : store.textDocs.length > 1 ? 'multi' : store.textDocs[0]?.context_mode ?? 'full',
          }
        : undefined

    // Build Code Interpreter files payload
    const files = store.codeInterpreterDocs.length > 0
      ? store.codeInterpreterDocs.map((d) => ({
          name: d.name,
          media_type: d.media_type,
          data: d.data,
        }))
      : undefined

    try {
      const response = await fetch('/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: store.sessionId,
          web_search: store.webSearchEnabled,
          locale: i18n.global.locale.value,
          session_attributes: sessionAttributes,
          files,
        }),
      })

      if (!response.ok || !response.body) {
        store.updateLastAssistantMessage(i18n.global.t('error_server'))
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
            }, (label) => {
              store.streamingStatus = label
            }, () => {
              store.setCitations([...citations])
            })
          }
        }
      }

      store.setTraceSteps(traceSteps)
      store.setCitations(citations)

      // Extract action groups/tools used from trace steps
      const toolsUsed: string[] = []
      const callingPrefixes = ['Aufruf: ', 'Appel : ', 'Chiamata: ', 'Calling: ']
      for (const step of traceSteps) {
        for (const prefix of callingPrefixes) {
          if (step.label.startsWith(prefix)) {
            toolsUsed.push(step.label.slice(prefix.length))
            break
          }
        }
      }

      // Auto-save interaction to S3 (with rating=null) so all interactions are logged
      const msgIndex = store.messages.length - 1
      if (fullText) {
        try {
          const payload: FeedbackPayload = {
            session_id: store.sessionId,
            message_index: msgIndex,
            rating: null,
            user_query: message,
            agent_response: fullText,
            agent_variant: store.webSearchEnabled ? 'web_search' : 'default',
            retrieved_chunks: citations.map((c) => ({ text: c.text, source: c.source })),
            tools_used: toolsUsed,
          }
          const res = await backendHttp.post<{ s3_key: string | null; timestamp: string | null }>(
            'v1/feedback',
            payload,
          )
          // Store S3 key and timestamp so subsequent ratings overwrite the same file
          const assistantMsg = store.messages[msgIndex]
          if (assistantMsg && assistantMsg.role === 'assistant') {
            assistantMsg.feedbackS3Key = res.data.s3_key
            assistantMsg.feedbackTimestamp = res.data.timestamp
          }
        } catch {
          // Silent fail — auto-save is best-effort
        }
      }
    } catch (error) {
      store.updateLastAssistantMessage(i18n.global.t('error_connection'))
    } finally {
      store.streamingStatus = ''
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
  onTrace: (label: string) => void,
  onCitation: () => void,
) {
  try {
    const parsed = JSON.parse(data)

    switch (eventType) {
      case 'token':
        onToken(parsed.text)
        break
      case 'trace':
        traceSteps.push({ label: parsed.label, detail: parsed.detail })
        onTrace(parsed.label)
        break
      case 'citation':
        citations.push({ source: parsed.source, text: parsed.text, source_type: parsed.source_type })
        onCitation()
        break
      case 'error':
        onToken(`\n\n⚠️ ${parsed.detail || i18n.global.t('error_generic')}`)
        break
      case 'done':
        break
    }
  } catch {
    // Skip malformed events
  }
}
