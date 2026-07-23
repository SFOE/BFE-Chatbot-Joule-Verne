import { ref } from 'vue'
import { backendHttp } from '@/services/http'
import { useChatStore } from '@/stores/chatStore'
import type { DocumentUploadResponse } from '@/types/chat'

/**
 * Composable for document upload handling.
 */
export function useDocuments() {
  const uploading = ref(false)
  const uploadErrors = ref<{ name: string; error: string }[]>([])

  async function uploadFiles(files: File[]) {
    const store = useChatStore()
    const totalDocs = store.textDocs.length + store.codeInterpreterDocs.length

    if (totalDocs + files.length > 5) {
      uploadErrors.value = [{ name: 'upload', error: 'Maximal 5 Dateien insgesamt erlaubt.' }]
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
    } catch (error) {
      uploadErrors.value = [{ name: 'upload', error: 'Upload fehlgeschlagen.' }]
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
