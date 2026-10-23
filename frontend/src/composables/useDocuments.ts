import { ref } from 'vue'
import axios from 'axios'
import { backendHttp } from '@/services/http'
import { useChatStore } from '@/stores/chatStore'
import { deleteSessionFile } from '@/services/conversations'
import type { DocumentUploadResponse } from '@/types/chat'
import i18n from '@/i18n'

/**
 * Composable for document upload handling.
 */
export function useDocuments() {
  const uploading = ref(false)
  const uploadErrors = ref<{ name: string; error: string; sensitivity_blocked?: boolean }[]>([])

  async function uploadFiles(files: File[]) {
    const store = useChatStore()
    const totalDocs =
      store.textDocs.length + store.codeInterpreterDocs.length + store.indexedDocs.length

    if (totalDocs + files.length > 50) {
      uploadErrors.value = [{ name: 'upload', error: i18n.global.t('error_max_files') }]
      return
    }

    uploading.value = true
    store.isUploading = true
    uploadErrors.value = []

    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }
    // The backend scopes the server-side index to this chat session.
    formData.append('session_id', store.sessionId)

    try {
      const response = await backendHttp.post<DocumentUploadResponse>(
        'v1/documents/upload',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )

      // Append to existing docs instead of replacing
      store.textDocs = [...store.textDocs, ...response.data.text_docs]
      store.codeInterpreterDocs = [...store.codeInterpreterDocs, ...response.data.code_interpreter_docs]
      store.indexedDocs = [...store.indexedDocs, ...response.data.indexed_docs]
      // Accumulate the agent-facing summary of indexed docs across batches.
      if (response.data.document_summary) {
        store.documentSummary = store.documentSummary
          ? store.documentSummary + '\n' + response.data.document_summary
          : response.data.document_summary
      }
      uploadErrors.value = response.data.errors
    } catch (error: unknown) {
      let errorMsg = i18n.global.t('error_upload')
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        errorMsg = error.response.data.detail
      }
      uploadErrors.value = [{ name: 'upload', error: errorMsg }]
    } finally {
      uploading.value = false
      store.isUploading = false
    }
  }

  async function removeDocument(fileId: string) {
    const store = useChatStore()
    try {
      await deleteSessionFile(store.sessionId, fileId)
      // Remove from whichever list holds it (server deleted original + index).
      store.indexedDocs = store.indexedDocs.filter((d) => d.file_id !== fileId)
      store.codeInterpreterDocs = store.codeInterpreterDocs.filter((d) => d.file_id !== fileId)
      store.textDocs = store.textDocs.filter((d) => d.file_id !== fileId)
    } catch {
      // Leave the entry so the user can retry.
    }
  }

  return { uploading, uploadErrors, uploadFiles, removeDocument }
}
