<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <footer class="footer">
    <router-link to="/release-notes">{{ t('release_notes_link') }}</router-link>
    <span class="footer-divider">|</span>
    <a href="mailto:digitalisierung@bfe.admin.ch">{{ t('footer_contact') }}</a>
    <span class="footer-divider">|</span>
    <a href="https://www.admin.ch/gov/de/start/rechtliches.html" target="_blank" rel="noopener">
      {{ t('footer_legal') }}
    </a>
  </footer>
</template>
