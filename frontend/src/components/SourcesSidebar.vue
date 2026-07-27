<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

interface ResolvedSource {
  type: 'web' | 'website' | 'fedlex' | 'document'
  url: string
  label: string
}

const { t } = useI18n()
const store = useChatStore()
const resolvedSources = ref<ResolvedSource[]>([])

watch(
  () => store.citations,
  async (citations) => {
    if (!citations.length) {
      resolvedSources.value = []
      return
    }

    const seen = new Set<string>()
    const sources: ResolvedSource[] = []

    for (const citation of citations) {
      const src = citation.source
      if (!src || seen.has(src)) continue
      seen.add(src)

      // Direct web URLs
      if (src.startsWith('http')) {
        sources.push({ type: 'web', url: src, label: src })
        continue
      }

      // S3 URIs — resolve via backend
      if (src.startsWith('s3://')) {
        try {
          const res = await fetch(`/v1/sources/metadata?uri=${encodeURIComponent(src)}`)
          if (!res.ok) continue
          const meta = await res.json()

          if (meta.type === 'website' && meta.source_url) {
            if (!seen.has(meta.source_url)) {
              seen.add(meta.source_url)
              sources.push({ type: 'website', url: meta.source_url, label: meta.source_url })
            }
          } else if (meta.type === 'fedlex' && meta.fedlex_url) {
            if (!seen.has(meta.fedlex_url)) {
              seen.add(meta.fedlex_url)
              const label =
                meta.abbreviation && meta.title
                  ? `${meta.abbreviation} – ${meta.title}`
                  : meta.title || meta.filename
              sources.push({ type: 'fedlex', url: meta.fedlex_url, label })
            }
          } else if (meta.type === 'document') {
            // Get a presigned download URL for the PDF
            try {
              const dlRes = await fetch(`/v1/sources/download?uri=${encodeURIComponent(src)}`)
              if (dlRes.ok) {
                const dlData = await dlRes.json()
                const filename = dlData.filename.replace(/(_part\d+)?\.txt$/, '.pdf')
                if (!seen.has(filename)) {
                  seen.add(filename)
                  sources.push({ type: 'document', url: dlData.url, label: filename })
                }
              }
            } catch {
              // Skip if download URL fails
            }
          }
        } catch {
          // Skip unresolvable sources
        }
      }
    }

    resolvedSources.value = sources
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
  color: #333;
  text-decoration: none;
  word-break: break-all;
}

.source-item a:hover {
  text-decoration: underline;
}
</style>
