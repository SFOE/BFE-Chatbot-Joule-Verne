<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Citation } from '@/types/chat'
import {
  resolveSources,
  type ResolvedSource,
  type SourceType,
} from '@/composables/useSources'

const props = defineProps<{
  citations: Citation[]
}>()

const { t } = useI18n()
const expanded = ref(false)
const resolved = ref<ResolvedSource[]>([])

// Stable display order for the type groups.
const GROUP_ORDER: SourceType[] = [
  'document',
  'website',
  'fedlex',
  'specific',
  'aramis',
  'web',
]

// Resolve whenever the citations change. s3:// links are re-resolved at display
// time so presigned download URLs stay fresh for stored (older) chats.
watch(
  () => props.citations,
  async (citations) => {
    resolved.value = await resolveSources(citations ?? [])
  },
  { immediate: true, deep: true },
)

const groups = computed(() => {
  const byType = new Map<SourceType, ResolvedSource[]>()
  for (const src of resolved.value) {
    const list = byType.get(src.type) ?? []
    list.push(src)
    byType.set(src.type, list)
  }
  return GROUP_ORDER.filter((type) => byType.has(type)).map((type) => ({
    type,
    label: t(`source_group_${type}`),
    sources: byType.get(type)!,
  }))
})
</script>

<template>
  <details
    v-if="resolved.length"
    class="message-sources"
    :open="expanded"
    @toggle="expanded = ($event.target as HTMLDetailsElement).open"
  >
    <summary>{{ t('message_sources_title', { count: resolved.length }) }}</summary>
    <div class="message-sources__groups">
      <div v-for="group in groups" :key="group.type" class="message-sources__group">
        <span class="message-sources__group-label">{{ group.label }}</span>
        <ul>
          <li v-for="(source, i) in group.sources" :key="i">
            <a :href="source.url" target="_blank" rel="noopener">{{ source.label }}</a>
          </li>
        </ul>
      </div>
    </div>
  </details>
</template>

<style scoped>
.message-sources {
  margin-top: 0.4rem;
  font-size: 0.8rem;
}

.message-sources summary {
  cursor: pointer;
  opacity: 0.8;
}

.message-sources__groups {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.4rem;
}

.message-sources__group-label {
  font-weight: 600;
  opacity: 0.7;
  font-size: 0.75rem;
}

.message-sources__group ul {
  list-style: none;
  margin: 0.2rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.message-sources__group a {
  color: #1a73e8;
  text-decoration: none;
  word-break: break-all;
}

.message-sources__group a:hover {
  text-decoration: underline;
}
</style>
