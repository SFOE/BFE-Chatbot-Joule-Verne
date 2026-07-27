<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { backendHttp } from '@/services/http'
import MarkdownIt from 'markdown-it'

const { t } = useI18n()
const md = new MarkdownIt({ linkify: true, breaks: true })

interface Release {
  name: string
  tag: string
  date: string
  body: string
  prerelease: boolean
}

const releases = ref<Release[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const response = await backendHttp.get<Release[]>('v1/releases')
    releases.value = response.data
  } catch {
    releases.value = []
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="release-notes">
    <h2>📋 {{ t('release_notes_title') }}</h2>

    <p v-if="loading">Laden...</p>

    <div v-else-if="releases.length" class="releases-list">
      <article v-for="release in releases" :key="release.tag" class="release-item">
        <header class="release-header">
          <h3>{{ release.name }}</h3>
          <time :datetime="release.date">{{ release.date }}</time>
          <span v-if="release.prerelease" class="prerelease-badge">Pre-release</span>
        </header>
        <div class="release-body" v-html="md.render(release.body)" />
      </article>
    </div>

    <p v-else>Keine Release Notes verfügbar.</p>

    <router-link to="/" class="back-link">← {{ t('back_to_chat') }}</router-link>
  </div>
</template>
