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
  if (!inputText.value.trim() || store.isStreaming) return
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
      :placeholder="t('input_placeholder')"
      :disabled="store.isStreaming"
      rows="1"
      @keydown="handleKeydown"
      @input="autoResize"
    />
    <button
      class="send-button"
      :disabled="!inputText.trim() || store.isStreaming"
      @click="handleSubmit"
    >
      {{ t('send') }}
    </button>
  </div>
</template>
