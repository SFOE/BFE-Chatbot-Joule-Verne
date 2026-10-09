<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import { resolveSources, type ResolvedSource } from '@/composables/useSources'

const { t } = useI18n()
const store = useChatStore()
const resolvedSources = ref<ResolvedSource[]>([])

watch(
  () => [...store.citations],
  async (citations) => {
    resolvedSources.value = await resolveSources(citations)
  },
  { immediate: true },
)
</script>

<template>
  <aside class="sources-sidebar">
    <h3>{{ t('sources_title') }}</h3>

    <div v-if="resolvedSources.length" class="sources-list">
      <div v-for="(source, i) in resolvedSources" :key="i" class="source-item">
        <a :href="source.url" target="_blank" rel="noopener">
          {{ source.label }}
        </a>
      </div>
    </div>

    <p v-else class="no-sources">—</p>
  </aside>
</template>

<style scoped>
.sources-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.source-item a {
  font-size: 0.85em;
  color: var(--color-text);
  text-decoration: none;
  word-break: break-all;
}

.source-item a:hover {
  text-decoration: underline;
}
</style>
