<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import { useI18n } from 'vue-i18n'
import type { ChatMessage } from '@/types/chat'
import { useChatStore } from '@/stores/chatStore'
import TraceExpander from '@/components/TraceExpander.vue'
import FeedbackWidget from '@/components/FeedbackWidget.vue'

const props = defineProps<{
  message: ChatMessage
  index: number
}>()

const { t } = useI18n()
const store = useChatStore()
const md = new MarkdownIt({ linkify: true, breaks: true })

const renderedContent = computed(() => {
  if (props.message.role === 'assistant') {
    return md.render(props.message.content)
  }
  return props.message.content
})

const isLastMessage = computed(() => props.index === store.messages.length - 1)
</script>

<template>
  <div class="chat-message" :class="`chat-message--${message.role}`">
    <div class="chat-message__bubble">
      <div v-if="message.role === 'assistant'" class="chat-message__content" v-html="renderedContent" />
      <p v-else class="chat-message__content">{{ message.content }}</p>
      <p v-if="message.role === 'assistant' && store.isStreaming && isLastMessage" class="streaming-status">
        {{ store.streamingStatus || t('thinking') }}
      </p>
    </div>

    <template v-if="message.role === 'assistant' && message.content && !store.isStreaming">
      <TraceExpander v-if="message.traceSteps?.length" :steps="message.traceSteps" />
      <FeedbackWidget :message-index="index" />
    </template>
  </div>
</template>
