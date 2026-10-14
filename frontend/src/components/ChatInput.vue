<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChat } from '@/composables/useChat'
import { useChatStore } from '@/stores/chatStore'

const { t } = useI18n()
const { sendMessage } = useChat()
const store = useChatStore()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const textarea = textareaRef.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
}

function handleSubmit() {
  // Block while a document is still uploading/indexing so the user can't ask
  // about it before its index exists.
  if (!inputText.value.trim() || store.isStreaming || store.isUploading) return
  sendMessage(inputText.value.trim())
  inputText.value = ''
  nextTick(() => autoResize())
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}
</script>

<template>
  <div class="chat-input">
    <textarea
      ref="textareaRef"
      v-model="inputText"
      :placeholder="store.isUploading ? t('upload_processing') : t('input_placeholder')"
      :disabled="store.isStreaming || store.isUploading"
      rows="1"
      @keydown="handleKeydown"
      @input="autoResize"
    />
    <button
      class="send-button"
      :disabled="!inputText.trim() || store.isStreaming || store.isUploading"
      @click="handleSubmit"
    >
      {{ t('send') }}
    </button>
  </div>
</template>
