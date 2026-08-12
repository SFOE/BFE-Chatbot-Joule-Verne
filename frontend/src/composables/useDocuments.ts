import { ref } from 'vue'
import axios from 'axios'
import { backendHttp } from '@/services/http'
import { useChatStore } from '@/stores/chatStore'
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
    const totalDocs = store.textDocs.length + store.codeInterpreterDocs.length

    if (totalDocs + files.length > 5) {
      uploadErrors.value = [{ name: 'upload', error: i18n.global.t('error_max_files') }]
      return
    }

    uploading.value = true
    uploadErrors.value = []

    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    try {
      const response = await backendHttp.post<DocumentUploadResponse>(
        'v1/documents/upload',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )

      // Append to existing docs instead of replacing
      store.textDocs = [...store.textDocs, ...response.data.text_docs]
      store.codeInterpreterDocs = [...store.codeInterpreterDocs, ...response.data.code_interpreter_docs]
      uploadErrors.value = response.data.errors
    } catch (error: unknown) {
      let errorMsg = i18n.global.t('error_upload')
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        errorMsg = error.response.data.detail
      }
      uploadErrors.value = [{ name: 'upload', error: errorMsg }]
    } finally {
      uploading.value = false
    }
  }

  function clearDocuments() {
    const store = useChatStore()
    store.textDocs = []
    store.codeInterpreterDocs = []
    uploadErrors.value = []
  }

  return { uploading, uploadErrors, uploadFiles, clearDocuments }
}
