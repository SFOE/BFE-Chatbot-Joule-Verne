<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import ChatWindow from '@/components/ChatWindow.vue'
import ChatInput from '@/components/ChatInput.vue'
import SearchModeToggle from '@/components/SearchModeToggle.vue'
import DocumentUpload from '@/components/DocumentUpload.vue'
import SourcesSidebar from '@/components/SourcesSidebar.vue'

const { t } = useI18n()
const store = useChatStore()
</script>

<template>
  <div class="chat-view">
    <aside class="sidebar">
      <div class="sidebar-section">
        <h3>{{ t('settings_title') }}</h3>
        <SearchModeToggle />
      </div>

      <div class="sidebar-section">
        <DocumentUpload />
      </div>

      <div class="sidebar-section">
        <button class="clear-chat-btn" @click="store.clearChat()">
          {{ t('clear_chat') }}
        </button>
      </div>

      <SourcesSidebar />
    </aside>

    <section class="chat-main">
      <p class="disclaimer">{{ t('disclaimer') }}</p>
      <ChatWindow />
      <ChatInput />
    </section>
  </div>
</template>
