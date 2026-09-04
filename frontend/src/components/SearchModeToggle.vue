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
  'web_search',
  'code_interpreter',
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

function selectKbMode() {
  if (store.searchModeLocked) return
  store.disableCustomMode()
  store.setSpecificKb(null)
  store.setWebSearch(false)
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

function selectWebMode() {
  if (store.searchModeLocked) return
  if (!store.webSearchEnabled) {
    showConfirmDialog.value = true
  }
}

function selectSpecificKb(kbId: string) {
  if (store.searchModeLocked) return
  store.setSpecificKb(kbId)
}

function confirmWebSearch() {
  if (pendingCustomWebSearch.value) {
    store.toggleCustomTool('web_search')
    pendingCustomWebSearch.value = false
  } else {
    store.setSpecificKb(null)
    store.setWebSearch(true)
  }
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
      <label :class="{ active: store.webSearchEnabled, disabled: store.searchModeLocked }">
        <input
          type="radio"
          name="searchMode"
          :checked="store.webSearchEnabled"
          :disabled="store.searchModeLocked"
          @change="selectWebMode"
        />
        {{ t('search_mode_web') }}
      </label>
    </div>

    <!-- Specific knowledge bases -->
    <template v-if="specificKbs.length">
      <span class="toggle-label toggle-label--sub">{{ t('search_mode_specific_label') }}</span>
      <div class="toggle-options">
        <label
          v-for="kb in specificKbs"
          :key="kb.id"
          :class="{ active: store.specificKbId === kb.id, disabled: store.searchModeLocked }"
        >
          <input
            type="radio"
            name="searchMode"
            :checked="store.specificKbId === kb.id"
            :disabled="store.searchModeLocked"
            @change="selectSpecificKb(kb.id)"
          />
          {{ kbName(kb) }}
        </label>
      </div>
    </template>

    <!-- Own choice (custom tool selection) -->
    <div class="toggle-options">
      <label :class="{ active: store.customMode, disabled: store.searchModeLocked }">
        <input
          type="radio"
          name="searchMode"
          :checked="store.customMode"
          :disabled="store.searchModeLocked"
          @change="selectCustomMode"
        />
        {{ t('search_mode_custom') }}
      </label>
    </div>

    <template v-if="store.customMode">
      <span class="toggle-label toggle-label--sub">{{ t('search_mode_custom_label') }}</span>
      <div class="tool-options">
        <label
          v-for="tool in CUSTOM_TOOLS"
          :key="tool"
          :class="{ active: store.customTools.has(tool), disabled: store.searchModeLocked }"
        >
          <input
            type="checkbox"
            :checked="store.customTools.has(tool)"
            :disabled="store.searchModeLocked"
            @change="toggleTool(tool)"
          />
          {{ toolLabel(tool) }}
        </label>
      </div>

      <!-- Specific knowledge bases (selectable alongside the tools above) -->
      <template v-if="specificKbs.length">
        <span class="toggle-label toggle-label--sub">{{ t('search_mode_specific_label') }}</span>
        <div class="tool-options">
          <label
            v-for="kb in specificKbs"
            :key="kb.id"
            :class="{ active: store.customKbIds.has(kb.id), disabled: store.searchModeLocked }"
          >
            <input
              type="checkbox"
              :checked="store.customKbIds.has(kb.id)"
              :disabled="store.searchModeLocked"
              @change="toggleKb(kb.id)"
            />
            {{ kbName(kb) }}
          </label>
        </div>
      </template>
    </template>

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
  gap: 0.4rem;
  cursor: pointer;
}

.tool-options label.disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
