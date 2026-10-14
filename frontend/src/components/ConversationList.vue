<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import {
  listConversations,
  renameConversation,
  deleteConversation,
  type ConversationSummary,
} from '@/services/conversations'

const { t } = useI18n()
const store = useChatStore()

const conversations = ref<ConversationSummary[]>([])

async function refresh() {
  if (!store.saveChatsEnabled) {
    conversations.value = []
    return
  }
  try {
    conversations.value = await listConversations()
  } catch {
    conversations.value = []
  }
}

// Refresh when saving gets enabled and whenever a new answer may have been
// persisted (message count grows while not streaming).
watch(
  () => store.saveChatsEnabled,
  () => refresh(),
  { immediate: true },
)
watch(
  () => [store.messages.length, store.isStreaming],
  ([, streaming], [, prevStreaming]) => {
    // Fires when a streamed answer just completed.
    if (prevStreaming && !streaming) refresh()
  },
)

async function open(id: string) {
  if (store.isStreaming || id === store.sessionId) return
  try {
    await store.openConversation(id)
  } catch {
    // Ignore — a stale list entry simply won't open.
  }
}

function startNewChat() {
  if (store.isStreaming) return
  store.clearChat()
}

async function rename(convo: ConversationSummary) {
  const next = window.prompt(t('conversations_rename'), convo.title)
  if (next == null) return
  const trimmed = next.trim()
  if (!trimmed || trimmed === convo.title) return
  try {
    const updated = await renameConversation(convo.session_id, trimmed)
    convo.title = updated.title
  } catch {
    // Ignore rename failures.
  }
}

async function remove(convo: ConversationSummary) {
  if (store.isStreaming) return
  if (!window.confirm(t('conversations_delete_confirm'))) return
  try {
    await deleteConversation(convo.session_id)
    conversations.value = conversations.value.filter(
      (c) => c.session_id !== convo.session_id,
    )
    // If the open chat was deleted, start a fresh one.
    if (convo.session_id === store.sessionId) {
      store.clearChat()
    }
  } catch {
    // Ignore delete failures — the entry stays and can be retried.
  }
}
</script>

<template>
  <div class="conversation-list">
    <div class="conversation-list__header">
      <h3>{{ t('conversations_title') }}</h3>
      <button class="conversation-list__new" :disabled="store.isStreaming" @click="startNewChat">
        + {{ t('conversations_new') }}
      </button>
    </div>

    <p v-if="!conversations.length" class="conversation-list__empty">
      {{ store.saveChatsEnabled ? t('conversations_empty') : t('conversations_disabled') }}
    </p>

    <ul v-else class="conversation-list__items">
      <li
        v-for="convo in conversations"
        :key="convo.session_id"
        :class="{ active: convo.session_id === store.sessionId }"
      >
        <button class="conversation-list__title" :title="convo.title" @click="open(convo.session_id)">
          {{ convo.title }}
        </button>
        <button
          class="conversation-list__action"
          :title="t('conversations_rename')"
          @click="rename(convo)"
        >
          ✎
        </button>
        <button
          class="conversation-list__action conversation-list__action--delete"
          :title="t('conversations_delete')"
          @click="remove(convo)"
        >
          🗑
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.conversation-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.conversation-list__new {
  font-size: 0.75rem;
  padding: 2px 8px;
  cursor: pointer;
}

.conversation-list__new:disabled {
  opacity: 0.5;
  cursor: default;
}

.conversation-list__empty {
  font-size: 0.8rem;
  opacity: 0.7;
}

.conversation-list__items {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.conversation-list__items li {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: 4px;
}

.conversation-list__items li.active {
  background: rgba(26, 115, 232, 0.12);
}

.conversation-list__title {
  flex: 1;
  min-width: 0;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 4px 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.conversation-list__action {
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.5;
  font-size: 0.8rem;
  padding: 2px 4px;
}

.conversation-list__action:hover {
  opacity: 1;
}

.conversation-list__action--delete:hover {
  color: #c0392b;
}
</style>
