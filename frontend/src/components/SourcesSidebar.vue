<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

const { t } = useI18n()
const store = useChatStore()
</script>

<template>
  <aside class="sources-sidebar">
    <h3>{{ t('sources_title') }}</h3>

    <div v-if="store.citations.length" class="sources-list">
      <div v-for="(citation, i) in store.citations" :key="i" class="source-item">
        <a
          v-if="citation.source.startsWith('http')"
          :href="citation.source"
          target="_blank"
          rel="noopener"
        >
          🌐 {{ citation.source }}
        </a>
        <span v-else class="source-s3">📃 {{ citation.source }}</span>
      </div>
    </div>

    <p v-else class="no-sources">—</p>
  </aside>
</template>
