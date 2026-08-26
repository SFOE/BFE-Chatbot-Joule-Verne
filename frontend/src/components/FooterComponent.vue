<template>
  <footer class="site-footer full-bleed">
    <div class="footer-inner app-container">
      <div class="footer-left">
        <ul class="footer-links">
          <li>{{ t('header_title') }}</li>
        </ul>
      </div>

      <div class="footer-center">
        <ul class="footer-links">
          <li>
            <a href="https://www.admin.ch/gov/de/start/rechtliches.html" target="_blank" rel="noopener">
              {{ t('footer_legal') }}
            </a>
          </li>
          <li>
            <a href="mailto:digitalisierung@bfe.admin.ch">{{ t('footer_contact') }}</a>
          </li>
          <li>
            <router-link to="/release-notes">{{ t('release_notes_link') }}</router-link>
          </li>
          <li>
            <router-link to="/kb-upload">{{ t('kb_upload_link') }}</router-link>
          </li>
        </ul>
      </div>

      <div class="footer-right">
        <p>&copy; {{ new Date().getFullYear() }}</p>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped>
.site-footer {
  background-color: var(--color-primary);
  color: #fff;
  font-size: 0.8rem;
  line-height: 1.4;
  padding: 12px 0;
}

.footer-inner {
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
}

.footer-links {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  gap: 24px;
}

.site-footer a {
  color: rgba(255, 255, 255, 0.85);
  text-decoration: none;
  transition: color 0.2s ease;
}

.site-footer a:hover {
  color: #fff;
  text-decoration: underline;
}

.footer-right p {
  margin: 0;
  text-align: right;
  color: rgba(255, 255, 255, 0.7);
}

@media (max-width: 768px) {
  .footer-inner {
    flex-direction: column;
    text-align: center;
    gap: 16px;
  }

  .footer-links {
    flex-direction: column;
    gap: 8px;
  }

  .footer-right {
    text-align: center;
  }
}
</style>
