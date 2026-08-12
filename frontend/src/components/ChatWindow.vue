<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chatStore'
import ChatMessage from '@/components/ChatMessage.vue'

const store = useChatStore()
const chatWindowRef = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (chatWindowRef.value) {
      chatWindowRef.value.scrollTop = chatWindowRef.value.scrollHeight
    }
  })
}

watch(
  () => store.messages.length,
  () => scrollToBottom()
)

// Also scroll when streaming content updates the last message
watch(
  () => store.messages[store.messages.length - 1]?.content,
  () => scrollToBottom()
)
</script>

<template>
  <div ref="chatWindowRef" class="chat-window">
    <ChatMessage
      v-for="(msg, index) in store.messages"
      :key="index"
      :message="msg"
      :index="index"
    />
  </div>
</template>
