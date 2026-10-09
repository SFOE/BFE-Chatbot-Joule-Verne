import { backendHttp } from '@/services/http'
import type { ChatMessage } from '@/types/chat'

/**
 * Client for the persistent per-user chat endpoints.
 *
 * Covers the save opt-in preference plus list / save / load / rename of
 * conversations. Delete is added with Baustein 5.
 */

export interface SavePreference {
  save_enabled: boolean
}

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

/** Read whether the current user has opted in to saving chats. */
export async function getSavePreference(): Promise<boolean> {
  const res = await backendHttp.get<SavePreference>('v1/conversations/preference')
  return res.data.save_enabled
}

/** Set the save opt-in flag. Returns the stored value. */
export async function setSavePreference(enabled: boolean): Promise<boolean> {
  const res = await backendHttp.put<SavePreference>('v1/conversations/preference', {
    save_enabled: enabled,
  })
  return res.data.save_enabled
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
