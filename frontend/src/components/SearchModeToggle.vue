<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

interface SpecificKb {
  id: string
  names: { de: string; fr: string; it: string; en: string }
}

const { t, locale } = useI18n()
const store = useChatStore()

const showConfirmDialog = ref(false)
// When set, confirming the web-search dialog toggles this custom tool instead
// of switching to classic web mode.
const pendingCustomWebSearch = ref(false)
const specificKbs = ref<SpecificKb[]>([])

// Selectable tools in "own choice" mode. Keys must match the agent's
// CAPABILITY_REGISTRY keys (agent-jouleverne/main.py).
const CUSTOM_TOOLS = [
  'kb_documents',
  'kb_website',
  'kb_legislation',
  'aramis',
] as const

function toolLabel(tool: string): string {
  return t(`tool_${tool}`)
}

onMounted(async () => {
  try {
    const response = await fetch('/v1/kbs/specific')
    if (response.ok) {
      specificKbs.value = await response.json()
    }
  } catch {
    // Silently ignore — specific KBs are optional
  }
})

function kbName(kb: SpecificKb): string {
  const loc = locale.value as keyof SpecificKb['names']
  return kb.names[loc] || kb.names.de || kb.id
}

const isKbMode = computed(
  () => !store.webSearchEnabled && !store.specificKbId && !store.customMode,
)

const isWebMode = computed(() => store.webSearchEnabled)

function selectKbMode() {
  if (store.searchModeLocked) return
  store.disableCustomMode()
  store.setSpecificKb(null)
  store.setWebSearch(false)
}

function selectWebMode() {
  if (store.searchModeLocked) return
  // Turning web search ON requires confirmation (external search service).
  if (!store.webSearchEnabled) {
    pendingCustomWebSearch.value = false
    showConfirmDialog.value = true
  }
}

function selectCustomMode() {
  if (store.searchModeLocked) return
  store.enableCustomMode()
}

function toggleTool(tool: string) {
  if (store.searchModeLocked) return
  // Turning web search ON requires the same confirmation as classic web mode.
  if (tool === 'web_search' && !store.customTools.has('web_search')) {
    pendingCustomWebSearch.value = true
    showConfirmDialog.value = true
    return
  }
  store.toggleCustomTool(tool)
}

function toggleKb(kbId: string) {
  if (store.searchModeLocked) return
  store.toggleCustomKb(kbId)
}

function confirmWebSearch() {
  if (pendingCustomWebSearch.value) {
    // Confirmation came from the "Eigene Auswahl" web_search checkbox.
    store.toggleCustomTool('web_search')
  } else {
    // Confirmation came from the standalone "Websuche" radio.
    store.setWebSearch(true)
  }
  pendingCustomWebSearch.value = false
  showConfirmDialog.value = false
}

function cancelWebSearch() {
  pendingCustomWebSearch.value = false
  showConfirmDialog.value = false
}
</script>

<template>
  <div class="search-mode-toggle">
    <span class="toggle-label">{{ t('search_mode_label') }}</span>
    <div class="toggle-options">
      <label :class="{ active: isKbMode, disabled: store.searchModeLocked }">
        <input
          type="radio"
          name="searchMode"
          :checked="isKbMode"
          :disabled="store.searchModeLocked"
          @change="selectKbMode"
        />
        {{ t('search_mode_kb') }}
      </label>
      <label :class="{ active: isWebMode, disabled: store.searchModeLocked }">
        <input
          type="radio"
          name="searchMode"
          :checked="isWebMode"
          :disabled="store.searchModeLocked"
          @change="selectWebMode"
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

<style scoped>
.toggle-label--sub {
  margin-top: 0.75rem;
  font-size: 0.85em;
  opacity: 0.8;
}

.tool-options {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.25rem;
}

.tool-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.tool-options label.disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
