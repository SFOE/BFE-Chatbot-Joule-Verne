<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import { backendHttp } from '@/services/http'
import type { FeedbackPayload } from '@/types/chat'

const { t } = useI18n()
const store = useChatStore()

const props = defineProps<{
  messageIndex: number
}>()

const rating = ref<'positive' | 'negative' | null>(null)
const showComment = ref(false)
const commentText = ref('')
const commentSaved = ref(false)

function getUserQuery(): string {
  for (let i = props.messageIndex - 1; i >= 0; i--) {
    if (store.messages[i].role === 'user') {
      return store.messages[i].content
    }
  }
  return ''
}

async function submitFeedback(newRating: 'positive' | 'negative') {
  rating.value = newRating

  const msg = store.messages[props.messageIndex]
  const payload: FeedbackPayload = {
    session_id: store.sessionId,
    message_index: props.messageIndex,
    rating: newRating,
    user_query: getUserQuery(),
    agent_response: msg.content,
    agent_variant: store.webSearchEnabled ? 'web_search' : 'default',
    retrieved_chunks: (msg.citations || []).map((c) => ({ text: c.text, source: c.source })),
    s3_key_override: msg.feedbackS3Key,
    original_timestamp: msg.feedbackTimestamp,
  }

  try {
    await backendHttp.post('v1/feedback', payload)
  } catch {
    // Silent fail — feedback is best-effort
  }
}

async function submitComment() {
  if (!commentText.value.trim()) return

  const msg = store.messages[props.messageIndex]
  const payload: FeedbackPayload = {
    session_id: store.sessionId,
    message_index: props.messageIndex,
    rating: rating.value,
    user_query: getUserQuery(),
    agent_response: msg.content,
    agent_variant: store.webSearchEnabled ? 'web_search' : 'default',
    comment: commentText.value.trim(),
    retrieved_chunks: (msg.citations || []).map((c) => ({ text: c.text, source: c.source })),
    s3_key_override: msg.feedbackS3Key,
    original_timestamp: msg.feedbackTimestamp,
  }

  try {
    await backendHttp.post('v1/feedback', payload)
    commentSaved.value = true
    showComment.value = false
  } catch {
    // Silent fail
  }
}
</script>

<template>
  <div class="feedback-widget">
    <div class="feedback-buttons">
      <button
        class="feedback-btn"
        :class="{ active: rating === 'positive' }"
        @click="submitFeedback('positive')"
        :title="t('feedback_good')"
      >
        👍
      </button>
      <button
        class="feedback-btn"
        :class="{ active: rating === 'negative' }"
        @click="submitFeedback('negative')"
        :title="t('feedback_bad')"
      >
        👎
      </button>
      <button
        v-if="!commentSaved"
        class="feedback-btn"
        @click="showComment = !showComment"
        :title="t('feedback_comment')"
      >
        💬
      </button>
      <span v-else class="feedback-saved">{{ t('feedback_saved') }}</span>
    </div>

    <div v-if="showComment" class="feedback-comment">
      <textarea
        v-model="commentText"
        :placeholder="t('feedback_comment_placeholder')"
        rows="2"
        maxlength="1000"
      />
      <button class="comment-send-btn" @click="submitComment">
        {{ t('feedback_send') }}
      </button>
    </div>
  </div>
</template>
