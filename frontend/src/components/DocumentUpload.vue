<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import { useDocuments } from '@/composables/useDocuments'

const { t } = useI18n()
const store = useChatStore()
const { uploading, uploadErrors, uploadFiles, clearDocuments, removeIndexedDoc } = useDocuments()

const fileInput = ref<HTMLInputElement | null>(null)

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  uploadFiles(Array.from(target.files))
  target.value = ''
}

function formatSensitivityError(error: string): string {
  // Backend sends structured keys like "sensitivity_label_blocked:L3"
  // or "sensitivity_keyword_blocked:GEHEIM"
  if (error.startsWith('sensitivity_label_blocked:')) {
    const label = error.split(':')[1]
    return t('error_sensitivity_label', { label })
  }
  if (error.startsWith('sensitivity_keyword_blocked:')) {
    const keyword = error.split(':')[1]
    return t('error_sensitivity_keyword', { keyword })
  }
  return error
}
</script>

<template>
  <div class="document-upload">
    <h3>{{ t('upload_title') }}</h3>

    <template v-if="store.webSearchEnabled">
      <p class="upload-disabled">{{ t('upload_disabled_web_search') }}</p>
    </template>

    <template v-else>
      <button class="file-select-btn" @click="fileInput?.click()">
        {{ t('file_select_btn') }}
      </button>
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.txt,.docx,.xlsx,.csv"
        class="file-input-hidden"
        @change="handleFileChange"
      />
      <p class="upload-hint">{{ t('upload_hint') }}</p>

      <p v-if="uploading" class="upload-status">⏳ {{ t('upload_processing') }}</p>

      <div v-if="store.textDocs.length" class="uploaded-docs">
        <p v-for="doc in store.textDocs" :key="doc.name" class="doc-success">
          📄 <strong>{{ doc.name }}</strong> ({{ t('doc_pages', { count: doc.page_count }) }}, {{ doc.context_mode }})
        </p>
      </div>

      <div v-if="store.codeInterpreterDocs.length" class="uploaded-docs">
        <p v-for="doc in store.codeInterpreterDocs" :key="doc.name" class="doc-success">
          📊 <strong>{{ doc.name }}</strong> (Code Interpreter)
        </p>
      </div>

      <div v-if="store.indexedDocs.length" class="uploaded-docs">
        <p v-for="doc in store.indexedDocs" :key="doc.doc_id" class="doc-success doc-indexed-row">
          <span>🔍 <strong>{{ doc.name }}</strong> ({{ t('doc_indexed') }})</span>
          <button
            v-if="doc.file_id"
            class="doc-remove-btn"
            :title="t('conversations_delete')"
            @click="removeIndexedDoc(doc.file_id)"
          >
            🗑
          </button>
        </p>
      </div>

      <div v-if="uploadErrors.length" class="upload-errors">
        <p v-for="err in uploadErrors" :key="err.name" :class="err.sensitivity_blocked ? 'doc-warning' : 'doc-error'">
          <template v-if="err.sensitivity_blocked">
            🔒 <strong>{{ err.name }}</strong>: {{ formatSensitivityError(err.error) }}
          </template>
          <template v-else>
            ❌ <strong>{{ err.name }}</strong>: {{ err.error }}
          </template>
        </p>
      </div>

      <button
        v-if="store.textDocs.length || store.codeInterpreterDocs.length || store.indexedDocs.length"
        class="remove-docs-btn"
        @click="clearDocuments"
      >
        🗑️ {{ t('upload_remove_all') }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.doc-indexed-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.doc-remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.5;
  font-size: 0.8rem;
  padding: 2px 4px;
}

.doc-remove-btn:hover {
  opacity: 1;
  color: #c0392b;
}
</style>
