<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import { useDocuments } from '@/composables/useDocuments'

const { t } = useI18n()
const store = useChatStore()
const { uploading, uploadErrors, uploadFiles, removeDocument } = useDocuments()

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

function confirmRemoveDocument(fileId: string) {
  const confirmed = window.confirm(
    'Möchtest du dieses Dokument wirklich entfernen?'
  )

  if (confirmed) {
    removeDocument(fileId)
  }
}
</script>

<template>
  <div class="document-upload">
    <h3>{{ t('upload_title') }}</h3>

    <template v-if="!store.uploadAllowed">
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
        <p v-for="doc in store.textDocs" :key="doc.name" class="doc-success doc-indexed-row">
          <span>
            📄 <strong>{{ doc.name }}</strong>
            <span class="doc-badge" :title="t('doc_tip_full')">{{ t('doc_label_full') }}</span>
          </span>
          <button
            v-if="doc.file_id"
            class="doc-remove-btn"
            :title="t('conversations_delete')"
            @click="confirmRemoveDocument(doc.file_id)"
          >
            🗑
          </button>
        </p>
      </div>

      <div v-if="store.codeInterpreterDocs.length" class="uploaded-docs">
        <p v-for="doc in store.codeInterpreterDocs" :key="doc.name" class="doc-success doc-indexed-row">
          <span>
            📊 <strong>{{ doc.name }}</strong>
            <span class="doc-badge" :title="t('doc_tip_table')">{{ t('doc_label_table') }}</span>
          </span>
          <button
            v-if="doc.file_id"
            class="doc-remove-btn"
            :title="t('conversations_delete')"
            @click="confirmRemoveDocument(doc.file_id)"
          >
            🗑
          </button>
        </p>
      </div>

      <div v-if="store.indexedDocs.length" class="uploaded-docs">
        <p v-for="doc in store.indexedDocs" :key="doc.doc_id" class="doc-success doc-indexed-row">
          <span>
            🔍 <strong>{{ doc.name }}</strong>
            <span class="doc-badge" :title="t('doc_tip_partial')">{{ t('doc_label_partial') }}</span>
          </span>
          <button
            v-if="doc.file_id"
            class="doc-remove-btn"
            :title="t('conversations_delete')"
            @click="confirmRemoveDocument(doc.file_id)"
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

.doc-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 0.72rem;
  background: rgba(0, 0, 0, 0.07);
  color: var(--color-text);
  cursor: help;
  white-space: nowrap;
}
</style>
