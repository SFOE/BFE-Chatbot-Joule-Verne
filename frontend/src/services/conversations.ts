import { backendHttp } from '@/services/http'
import type { ChatMessage, IndexedDoc } from '@/types/chat'

/**
 * Client for the persistent per-user chat endpoints.
 *
 * Covers the save opt-in preference plus list / save / load / rename of
 * conversations. Delete is added with Baustein 5.
 */

export interface ConversationSummary {
  session_id: string
  title: string
  updated_at: string
}

/** The persisted tool/mode selection, restored on continuation. */
export interface ModeConfig {
  customMode: boolean
  customTools: string[]
  customKbIds: string[]
  webSearchEnabled: boolean
  specificKbId: string | null
}

export interface ConversationDetail {
  session_id: string
  title: string
  updated_at: string
  mode_config: ModeConfig | null
  messages: ChatMessage[]
}

/** List the user's conversations, most recently updated first. */
export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await backendHttp.get<ConversationSummary[]>('v1/conversations')
  return res.data
}

/** Upsert a conversation's transcript + mode config. */
export async function saveConversation(
  sessionId: string,
  messages: ChatMessage[],
  modeConfig: ModeConfig,
): Promise<ConversationSummary> {
  const res = await backendHttp.put<ConversationSummary>('v1/conversations', {
    session_id: sessionId,
    messages,
    mode_config: modeConfig,
  })
  return res.data
}

/** Load a single conversation (metadata + transcript). */
export async function loadConversation(sessionId: string): Promise<ConversationDetail> {
  const res = await backendHttp.get<ConversationDetail>(
    `v1/conversations/${encodeURIComponent(sessionId)}`,
  )
  return res.data
}

/** Rename a conversation. */
export async function renameConversation(
  sessionId: string,
  title: string,
): Promise<ConversationSummary> {
  const res = await backendHttp.patch<ConversationSummary>(
    `v1/conversations/${encodeURIComponent(sessionId)}`,
    { title },
  )
  return res.data
}

/** Delete a conversation and all associated data. */
export async function deleteConversation(sessionId: string): Promise<void> {
  await backendHttp.delete(`v1/conversations/${encodeURIComponent(sessionId)}`)
}

/**
 * Immediately delete an opt-out session's short-lived agent transcript.
 * Idempotent and best-effort — used when saving is turned off or a new chat
 * is started so nothing lingers until the 1-day backstop.
 */
export async function deleteEphemeralSession(sessionId: string): Promise<void> {
  await backendHttp.delete(
    `v1/conversations/${encodeURIComponent(sessionId)}/ephemeral`,
  )
}

/** List the documents indexed for a session (to restore the UI on load). */
export async function listIndexedDocuments(sessionId: string): Promise<IndexedDoc[]> {
  const res = await backendHttp.get<IndexedDoc[]>('v1/documents/indexed', {
    params: { session_id: sessionId },
  })
  return res.data
}

export interface SessionFile {
  file_id: string
  name: string
  media_type: string
  routing: 'inline' | 'index' | 'ci' | string
  doc_id: string | null
}

/** List all files uploaded in a session (to restore the UI on continue). */
export async function listSessionFiles(sessionId: string): Promise<SessionFile[]> {
  const res = await backendHttp.get<SessionFile[]>('v1/documents/session-files', {
    params: { session_id: sessionId },
  })
  return res.data
}

/** Delete a single uploaded file (any type) from a session, by file_id. */
export async function deleteSessionFile(
  sessionId: string,
  fileId: string,
): Promise<void> {
  await backendHttp.delete(`v1/documents/${encodeURIComponent(fileId)}`, {
    params: { session_id: sessionId },
  })
}
