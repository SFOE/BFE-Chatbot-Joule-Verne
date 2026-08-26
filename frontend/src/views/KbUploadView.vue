<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

const { t, locale } = useI18n()

const kbs = ref<SpecificKb[]>([])
const selectedKbId = ref<string>('')
const uploading = ref(false)
const results = ref<UploadResult[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const ACCEPT = '.pdf,.txt,.md,.html,.doc,.docx,.csv,.xls,.xlsx'

onMounted(async () => {
  try {
    const response = await backendHttp.get<SpecificKb[]>('v1/kbs/specific')
    kbs.value = response.data
    if (kbs.value.length) {
      selectedKbId.value = kbs.value[0].id
    }
  } catch {
    kbs.value = []
  }
})

function kbName(kb: SpecificKb): string {
  const loc = locale.value as keyof SpecificKb['names']
  return kb.names[loc] || kb.names.de || kb.id
}

function triggerFileSelect() {
  fileInput.value?.click()
}

async function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length || !selectedKbId.value) return
  const files = Array.from(target.files)
  target.value = ''
  await uploadFiles(files)
}

async function uploadFiles(files: File[]) {
  uploading.value = true
  results.value = []

  for (const file of files) {
    try {
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
}
</script>

<template>
  <div class="kb-upload">
    <h2>{{ t('kb_upload_title') }}</h2>
    <p class="kb-upload-intro">{{ t('kb_upload_intro') }}</p>

    <div v-if="kbs.length" class="kb-upload-form">
      <label class="kb-select-label" for="kb-select">{{ t('kb_upload_select_label') }}</label>
      <select id="kb-select" v-model="selectedKbId" class="kb-select" :disabled="uploading">
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

.back-link {
  display: inline-block;
  margin-top: 1.5rem;
}
</style>
