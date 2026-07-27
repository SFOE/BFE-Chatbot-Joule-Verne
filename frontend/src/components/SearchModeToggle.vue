<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

const { t } = useI18n()
const store = useChatStore()

const showConfirmDialog = ref(false)

function setMode(webSearch: boolean) {
  if (store.searchModeLocked) return

  if (webSearch && !store.webSearchEnabled) {
    // Show confirmation before enabling web search
    showConfirmDialog.value = true
  } else {
    store.setWebSearch(webSearch)
  }
}

function confirmWebSearch() {
  store.setWebSearch(true)
  showConfirmDialog.value = false
}

function cancelWebSearch() {
  showConfirmDialog.value = false
}
</script>

<template>
  <div class="search-mode-toggle">
    <span class="toggle-label">{{ t('search_mode_label') }}</span>
    <div class="toggle-options">
      <label :class="{ active: !store.webSearchEnabled, disabled: store.searchModeLocked }">
        <input
          type="radio"
          name="searchMode"
          :checked="!store.webSearchEnabled"
          :disabled="store.searchModeLocked"
          @change="setMode(false)"
        />
        {{ t('search_mode_kb') }}
      </label>
      <label :class="{ active: store.webSearchEnabled, disabled: store.searchModeLocked }">
        <input
          type="radio"
          name="searchMode"
          :checked="store.webSearchEnabled"
          :disabled="store.searchModeLocked"
          @change="setMode(true)"
        />
        {{ t('search_mode_web') }}
      </label>
    </div>

    <!-- Confirmation dialog -->
    <div v-if="showConfirmDialog" class="confirm-overlay" @click.self="cancelWebSearch">
      <div class="confirm-dialog">
        <h4>⚠️ {{ t('web_search_confirm_title') }}</h4>
        <p>{{ t('web_search_confirm_body') }}</p>
        <div class="confirm-actions">
          <button class="confirm-btn confirm-btn--yes" @click="confirmWebSearch">
            {{ t('web_search_confirm_yes') }}
          </button>
          <button class="confirm-btn confirm-btn--no" @click="cancelWebSearch">
            {{ t('web_search_confirm_no') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
