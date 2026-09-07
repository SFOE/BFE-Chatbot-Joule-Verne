<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

interface ResolvedSource {
  type: 'web' | 'website' | 'fedlex' | 'document' | 'specific' | 'aramis'
  url: string
  label: string
}

const { t } = useI18n()
const store = useChatStore()
const resolvedSources = ref<ResolvedSource[]>([])

watch(
  () => [...store.citations],
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

      // Direct web URLs (web search results, ARAMIS links)
      if (src.startsWith('http')) {
        const type: ResolvedSource['type'] =
          citation.source_type === 'aramis' || citation.source_type === 'aramis_publication'
            ? 'aramis'
            : 'web'
        sources.push({ type, url: src, label: citation.text || src })
        continue
      }

      // S3 URIs — use source_type hint if available, then resolve via backend
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
          } else if (meta.type === 'specific') {
            // Specific-KB documents are ingested raw (no extraction pipeline),
            // so the S3 object is the citable document. Use the real filename
            // and link straight to the presigned download — no .txt -> .pdf rewrite.
            const filename = meta.filename || citation.text || src
            if (meta.download_url && !seen.has(meta.download_url)) {
              seen.add(meta.download_url)
              sources.push({ type: 'specific', url: meta.download_url, label: filename })
            }
          } else if (meta.type === 'document') {
            // Main corpus: extracted text (.txt) maps back to the source PDF.
            const filename = meta.pdf_filename || meta.filename
            if (!filename) continue
            const pdfName = filename.replace(/(_part\d+)?\.txt$/, '.pdf')
            if (!seen.has(pdfName)) {
              seen.add(pdfName)
              if (meta.download_url) {
                sources.push({ type: 'document', url: meta.download_url, label: pdfName })
              }
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
  color: var(--color-text);
  text-decoration: none;
  word-break: break-all;
}

.source-item a:hover {
  text-decoration: underline;
}
</style>
