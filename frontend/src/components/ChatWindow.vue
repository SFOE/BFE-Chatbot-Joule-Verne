<script setup lang="ts">
import { useChatStore } from '@/stores/chatStore'
import ChatMessage from '@/components/ChatMessage.vue'

const store = useChatStore()
</script>

<template>
  <div class="chat-window">
    <ChatMessage
      v-for="(msg, index) in store.messages"
      :key="index"
      :message="msg"
      :index="index"
    />
  </div>
</template>
