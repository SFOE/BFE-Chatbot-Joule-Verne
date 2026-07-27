<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import { useDocuments } from '@/composables/useDocuments'

const { t } = useI18n()
const store = useChatStore()
const { uploading, uploadErrors, uploadFiles, clearDocuments } = useDocuments()

const fileInput = ref<HTMLInputElement | null>(null)

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  uploadFiles(Array.from(target.files))
  target.value = ''
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
        Datei(en) auswählen
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
          📄 <strong>{{ doc.name }}</strong> ({{ doc.page_count }} Seiten, {{ doc.context_mode }})
        </p>
      </div>

      <div v-if="store.codeInterpreterDocs.length" class="uploaded-docs">
        <p v-for="doc in store.codeInterpreterDocs" :key="doc.name" class="doc-success">
          📊 <strong>{{ doc.name }}</strong> (Code Interpreter)
        </p>
      </div>

      <div v-if="uploadErrors.length" class="upload-errors">
        <p v-for="err in uploadErrors" :key="err.name" class="doc-error">
          ❌ <strong>{{ err.name }}</strong>: {{ err.error }}
        </p>
      </div>

      <button
        v-if="store.textDocs.length || store.codeInterpreterDocs.length"
        class="remove-docs-btn"
        @click="clearDocuments"
      >
        🗑️ {{ t('upload_remove_all') }}
      </button>
    </template>
  </div>
</template>
