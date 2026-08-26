<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { backendHttp } from '@/services/http'

interface SpecificKb {
  id: string
  names: { de: string; fr: string; it: string; en: string }
}

interface UploadResult {
  name: string
  status: 'success' | 'error'
  message?: string
}

interface KbFile {
  key: string
  name: string
  size: number
  last_modified: string
}

const { t, locale } = useI18n()

const kbs = ref<SpecificKb[]>([])
const selectedKbId = ref<string>('')
const uploading = ref(false)
const results = ref<UploadResult[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

// File list state
const files = ref<KbFile[]>([])
const loadingFiles = ref(false)
const deletingKey = ref<string | null>(null)
const currentPage = ref(1)
const PAGE_SIZE = 20

const totalPages = computed(() => Math.max(1, Math.ceil(files.value.length / PAGE_SIZE)))
const paginatedFiles = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return files.value.slice(start, start + PAGE_SIZE)
})
const selectedKbName = computed(() => {
  const kb = kbs.value.find((k) => k.id === selectedKbId.value)
  return kb ? kbName(kb) : ''
})

const ACCEPT = '.pdf,.txt,.md,.html,.doc,.docx,.csv,.xls,.xlsx,.jpeg,.jpg,.png'
const MAX_DOC_SIZE = 50 * 1024 * 1024 // 50 MB for documents
const MAX_IMAGE_SIZE = 3.75 * 1024 * 1024 // 3.75 MB for images
const IMAGE_EXTENSIONS = ['.jpeg', '.jpg', '.png']

onMounted(async () => {
  try {
    const response = await backendHttp.get<SpecificKb[]>('v1/kbs/specific')
    kbs.value = response.data
  } catch {
    kbs.value = []
  }
})

// Reload file list when selected KB changes
watch(selectedKbId, (newId) => {
  currentPage.value = 1
  if (newId) {
    loadFiles()
  } else {
    files.value = []
  }
})

function kbName(kb: SpecificKb): string {
  const loc = locale.value as keyof SpecificKb['names']
  return kb.names[loc] || kb.names.de || kb.id
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadFiles() {
  if (!selectedKbId.value) return
  loadingFiles.value = true
  try {
    const response = await backendHttp.get<KbFile[]>(`v1/kbs/${selectedKbId.value}/files`)
    files.value = response.data
  } catch {
    files.value = []
  } finally {
    loadingFiles.value = false
  }
}

async function deleteFile(file: KbFile) {
  if (!confirm(t('kb_files_delete_confirm', { name: file.name }))) return
  deletingKey.value = file.key
  try {
    await backendHttp.delete(`v1/kbs/${selectedKbId.value}/files`, { data: { key: file.key } })
    files.value = files.value.filter((f) => f.key !== file.key)
  } catch {
    alert(t('kb_files_delete_error'))
  } finally {
    deletingKey.value = null
  }
}

async function downloadFile(file: KbFile) {
  try {
    const { data } = await backendHttp.post<{ download_url: string }>(
      `v1/kbs/${selectedKbId.value}/download-url`,
      { key: file.key },
    )
    window.open(data.download_url, '_blank')
  } catch {
    alert(t('kb_files_download_error'))
  }
}

function triggerFileSelect() {
  fileInput.value?.click()
}

async function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length || !selectedKbId.value) return
  const fileList = Array.from(target.files)
  target.value = ''
  await uploadFiles(fileList)
}

async function uploadFiles(fileList: File[]) {
  uploading.value = true
  results.value = []

  for (const file of fileList) {
    try {
      // Check file size before requesting presigned URL
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      const isImage = IMAGE_EXTENSIONS.includes(ext)
      const maxSize = isImage ? MAX_IMAGE_SIZE : MAX_DOC_SIZE
      const maxLabel = isImage ? '3.75 MB' : '50 MB'

      if (file.size > maxSize) {
        results.value.push({
          name: file.name,
          status: 'error',
          message: t('kb_upload_error_too_large', { max: maxLabel }),
        })
        continue
      }

      // 1. Get a presigned URL from the backend
      const { data } = await backendHttp.post<{ upload_url: string; content_type: string }>(
        'v1/kbs/upload-url',
        { kb_id: selectedKbId.value, filename: file.name },
      )

      // 2. Upload the file directly to S3
      const putResponse = await fetch(data.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': data.content_type },
        body: file,
      })

      if (!putResponse.ok) {
        throw new Error(`S3 responded ${putResponse.status}`)
      }

      results.value.push({ name: file.name, status: 'success' })
    } catch (error: unknown) {
      let message = t('kb_upload_error_generic')
      if (typeof error === 'object' && error !== null && 'response' in error) {
        const resp = (error as { response?: { data?: { detail?: string } } }).response
        if (resp?.data?.detail) message = resp.data.detail
      }
      results.value.push({ name: file.name, status: 'error', message })
    }
  }

  uploading.value = false
  // Refresh file list after upload
  await loadFiles()
}
</script>

<template>
  <div class="kb-upload">
    <h2>{{ t('kb_upload_title') }}</h2>
    <p class="kb-upload-intro">{{ t('kb_upload_intro') }}</p>

    <div v-if="kbs.length" class="kb-upload-form">
      <label class="kb-select-label" for="kb-select">{{ t('kb_upload_select_label') }}</label>
      <select id="kb-select" v-model="selectedKbId" class="kb-select" :disabled="uploading">
        <option value="" disabled>{{ t('kb_upload_select_placeholder') }}</option>
        <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kbName(kb) }}</option>
      </select>

      <button class="file-select-btn" :disabled="uploading || !selectedKbId" @click="triggerFileSelect">
        {{ t('kb_upload_select_files') }}
      </button>
      <input
        ref="fileInput"
        type="file"
        multiple
        :accept="ACCEPT"
        class="file-input-hidden"
        @change="handleFileChange"
      />
      <p class="kb-upload-hint">{{ t('kb_upload_hint') }}</p>

      <p v-if="uploading" class="kb-upload-status">⏳ {{ t('kb_upload_uploading') }}</p>

      <div v-if="results.length" class="kb-upload-results">
        <p
          v-for="r in results"
          :key="r.name"
          :class="r.status === 'success' ? 'doc-success' : 'doc-error'"
        >
          <template v-if="r.status === 'success'">✅ <strong>{{ r.name }}</strong> — {{ t('kb_upload_done') }}</template>
          <template v-else>❌ <strong>{{ r.name }}</strong>: {{ r.message }}</template>
        </p>
      </div>

      <!-- File list -->
      <div v-if="selectedKbId" class="kb-files-section">
        <h3>{{ t('kb_files_title', { name: selectedKbName }) }}</h3>
        <p v-if="loadingFiles" class="kb-files-loading">{{ t('kb_files_loading') }}</p>
        <p v-else-if="!files.length" class="kb-files-empty">{{ t('kb_files_empty') }}</p>
        <table v-else class="kb-files-table">
          <thead>
            <tr>
              <th>{{ t('kb_files_col_name') }}</th>
              <th>{{ t('kb_files_col_size') }}</th>
              <th>{{ t('kb_files_col_date') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in paginatedFiles" :key="file.key">
              <td class="file-name">{{ file.name }}</td>
              <td>{{ formatSize(file.size) }}</td>
              <td>{{ formatDate(file.last_modified) }}</td>
              <td>
                <button
                  class="action-btn download-btn"
                  @click="downloadFile(file)"
                >
                  ⬇️
                </button>
                <button
                  class="action-btn delete-btn"
                  :disabled="deletingKey === file.key"
                  @click="deleteFile(file)"
                >
                  {{ deletingKey === file.key ? '...' : '🗑️' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="totalPages > 1" class="pagination">
          <button :disabled="currentPage <= 1" @click="currentPage--">←</button>
          <span>{{ currentPage }} / {{ totalPages }}</span>
          <button :disabled="currentPage >= totalPages" @click="currentPage++">→</button>
        </div>
      </div>
    </div>

    <p v-else>{{ t('kb_upload_none') }}</p>

    <router-link to="/" class="back-link">← {{ t('back_to_chat') }}</router-link>
  </div>
</template>

<style scoped>
.kb-upload {
  max-width: 720px;
  margin: 0 auto;
  padding: 1.5rem;
  overflow-y: auto;
  max-height: 100%;
}

.kb-upload-intro {
  color: var(--color-muted);
  margin-bottom: 1.5rem;
}

.kb-upload-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.kb-select-label {
  font-weight: 600;
}

.kb-select {
  padding: 0.5rem;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  max-width: 320px;
}

.file-input-hidden {
  display: none;
}

.kb-upload-hint {
  font-size: 0.85em;
  color: var(--color-muted);
}

.kb-upload-results {
  margin-top: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.kb-files-section {
  margin-top: 2rem;
}

.kb-files-section h3 {
  margin-bottom: 0.75rem;
}

.kb-files-loading,
.kb-files-empty {
  color: var(--color-muted);
  font-size: 0.9em;
}

.kb-files-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9em;
}

.kb-files-table th,
.kb-files-table td {
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.kb-files-table th {
  font-weight: 600;
  background: var(--color-surface);
}

.file-name {
  word-break: break-all;
  max-width: 300px;
}

.action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1em;
  padding: 0.25rem;
  border-radius: 4px;
}

.action-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.delete-btn:hover:not(:disabled) {
  background: #fee2e2;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.back-link {
  display: inline-block;
  margin-top: 1.5rem;
}

.pagination {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.pagination button {
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  cursor: pointer;
}

.pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pagination span {
  font-size: 0.85em;
  color: var(--color-muted);
}
</style>
