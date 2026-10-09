import type { Citation } from '@/types/chat'

export type SourceType =
  | 'web'
  | 'website'
  | 'fedlex'
  | 'document'
  | 'specific'
  | 'aramis'

export interface ResolvedSource {
  type: SourceType
  url: string
  label: string
}

/**
 * Resolve raw citations into deduplicated, linkable sources.
 *
 * - Direct http(s) URLs (web search, ARAMIS) are used as-is.
 * - s3:// URIs are resolved via the backend `/v1/sources/metadata` endpoint,
 *   which returns the citable URL/filename (and, for stored chats, keeps the
 *   presigned download links fresh because resolution happens at display time).
 *
 * Extracted from SourcesSidebar so it can back both the global sidebar and the
 * per-message source list.
 */
export async function resolveSources(citations: Citation[]): Promise<ResolvedSource[]> {
  if (!citations.length) return []

  const seen = new Set<string>()
  const sources: ResolvedSource[] = []

  for (const citation of citations) {
    const src = citation.source
    if (!src || seen.has(src)) continue
    seen.add(src)

    // Direct web URLs (web search results, ARAMIS links)
    if (src.startsWith('http')) {
      const type: SourceType =
        citation.source_type === 'aramis' || citation.source_type === 'aramis_publication'
          ? 'aramis'
          : 'web'
      sources.push({ type, url: src, label: citation.text || src })
      continue
    }

    // S3 URIs — resolve via backend metadata lookup.
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
          const filename = meta.filename || citation.text || src
          if (meta.download_url && !seen.has(meta.download_url)) {
            seen.add(meta.download_url)
            sources.push({ type: 'specific', url: meta.download_url, label: filename })
          }
        } else if (meta.type === 'document') {
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

  return sources
}
