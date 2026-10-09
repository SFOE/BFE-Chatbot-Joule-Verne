import { backendHttp } from '@/services/http'

/**
 * Client for the persistent per-user chat endpoints.
 *
 * This increment covers only the "save my chats" opt-in preference. List /
 * load / rename / delete follow in later increments.
 */

export interface SavePreference {
  save_enabled: boolean
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
