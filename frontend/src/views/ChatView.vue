<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import ChatWindow from '@/components/ChatWindow.vue'
import ChatInput from '@/components/ChatInput.vue'
import SearchModeToggle from '@/components/SearchModeToggle.vue'
import DocumentUpload from '@/components/DocumentUpload.vue'
import SourcesSidebar from '@/components/SourcesSidebar.vue'

interface ExternalLink {
  label: string
  url: string
  icon: string
  target: string
}

const { t } = useI18n()
const store = useChatStore()
const externalLinks = ref<ExternalLink[]>([])

onMounted(async () => {
  try {
    const response = await fetch('/v1/links')
    if (response.ok) {
      externalLinks.value = await response.json()
    }
  } catch {
    // Silently ignore — links are non-critical
  }
})
</script>

<template>
  <div class="chat-view">
    <aside class="sidebar">
      <div class="sidebar-section">
        <h3>{{ t('settings_title') }}</h3>
        <SearchModeToggle />
        <div v-if="externalLinks.length" class="external-links">
          <div v-for="(link, i) in externalLinks" :key="i" class="link-item">
            <a :href="link.url" :target="link.target" rel="noopener">
              {{ t('copilot_link') }}
            </a>
          </div>
        </div>
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

<style scoped>
.external-links {
  margin-top: 0.5rem;
}

.external-links .link-item a {
  font-size: 0.8em;
  color: var(--color-text);
  text-decoration: none;
}

.external-links .link-item a:hover {
  text-decoration: underline;
}
</style>
