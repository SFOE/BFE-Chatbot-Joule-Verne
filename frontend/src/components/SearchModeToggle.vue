<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

interface SpecificKb {
  id: string
  // Stable config slug (e.g. "gebaeudeprogramm", "interne-weisungen"); used to
  // resolve per-KB help texts. The id is the dynamic Bedrock KB id.
  slug?: string
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

// Plain-text link labels used to fill placeholders in tool/KB descriptions
// (e.g. {bfe}, {fedlex}, {gebaeudeprogramm}), so tooltips read cleanly.
const DESC_PLACEHOLDERS: Record<string, string> = {
  bfe: 'help_source_bfe',
  energieschweiz: 'help_source_energieschweiz',
  medienmitteilungen: 'help_source_medienmitteilungen',
  fedlex: 'help_source_fedlex',
  parlament: 'help_source_parlament',
  aramis: 'help_source_aramis',
  gebaeudeprogramm: 'help_source_gebaeudeprogramm',
  i14y: 'help_source_i14y',
}

function resolvePlaceholders(): Record<string, string> {
  const named: Record<string, string> = {}
  for (const [name, key] of Object.entries(DESC_PLACEHOLDERS)) {
    named[name] = t(key)
  }
  return named
}

// vue-i18n returns the key itself when a translation is missing.
function describe(key: string): string {
  const text = t(key, resolvePlaceholders())
  return text === key ? '' : text
}

// Tooltip description for a general tool, keyed on help_tool_<tool>_desc.
function toolDescription(tool: string): string {
  return describe(`help_tool_${tool}_desc`)
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

// The "Support" KB gets a dedicated top-level radio (between "Allgemeines
// BFE-Wissen" and "Websuche"), in addition to still appearing as a checkbox
// under "Spezifisches BFE-Wissen" for combining with other sources. Identified
// by the stable config slug ("support"); the id is a dynamic Bedrock KB id.
const supportKb = computed(() => specificKbs.value.find((kb) => kb.slug === 'support'))

// Tooltip description for a specific KB, keyed on help_kb_<slug>_desc. The
// backend sends a stable `slug` (the configured prefix, e.g. "interne-weisungen");
// the `id` is a dynamic Bedrock KB id and must not be used for the lookup.
// Separators are normalised to underscores to match the locale key style.
// Returns an empty string when no description exists for the KB.
function kbDescription(kb: SpecificKb): string {
  if (!kb.slug) return ''
  const slug = kb.slug
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return describe(`help_kb_${slug}_desc`)
}

const isKbMode = computed(
  () => !store.webSearchEnabled && !store.specificKbId && !store.customMode,
)

const isWebMode = computed(() => store.webSearchEnabled)

// Support is active when its (dynamic) KB id is the single selected specific KB.
const isSupportMode = computed(
  () => !!supportKb.value && store.specificKbId === supportKb.value.id,
)

function selectKbMode() {
  if (store.searchModeLocked) return
  store.disableCustomMode()
  store.setSpecificKb(null)
  store.setWebSearch(false)
}

function selectSupportMode() {
  if (store.searchModeLocked || !supportKb.value) return
  // Exclusive single-KB mode (clears web/custom), mirroring selectKbMode.
  store.setSpecificKb(supportKb.value.id)
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

  // Standardmässig vorausgewählte Wissensmöglichkeiten
  const defaultTools = [
    'kb_documents',
    'kb_website',
    'kb_legislation',
    'aramis',
  ]

  defaultTools.forEach((tool) => {
    if (!store.customTools.has(tool)) {
      store.toggleCustomTool(tool)
    }
  })
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
    <div class="toggle-options">
      <label
        :title="t('help_mode_kb_body')"
        :class="{ active: isKbMode, disabled: store.searchModeLocked }"
      >
        <input
          type="radio"
          name="searchMode"
          :checked="isKbMode"
          :disabled="store.searchModeLocked"
          @change="selectKbMode"
        />
        {{ t('search_mode_kb') }}
      </label>
      <label
        v-if="supportKb"
        :title="t('help_mode_support_body')"
        :class="{ active: isSupportMode, disabled: store.searchModeLocked }"
      >
        <input
          type="radio"
          name="searchMode"
          :checked="isSupportMode"
          :disabled="store.searchModeLocked"
          @change="selectSupportMode"
        />
        {{ t('search_mode_support') }}
      </label>
      <label
        :title="t('help_mode_web_body')"
        :class="{ active: isWebMode, disabled: store.searchModeLocked }"
      >
        <input
          type="radio"
          name="searchMode"
          :checked="isWebMode"
          :disabled="store.searchModeLocked"
          @change="selectWebMode"
        />
        {{ t('search_mode_web') }}
      </label>
      <label
        :title="t('help_mode_custom_body')"
        :class="{ active: store.customMode, disabled: store.searchModeLocked }"
      >
        <input
          type="radio"
          name="searchMode"
          :checked="store.customMode"
          :disabled="store.searchModeLocked"
          @change="selectCustomMode"
        />
        {{ t('search_mode_custom_label') }}
      </label>
    </div>

    <template v-if="store.customMode">
      <span class="toggle-label toggle-label--sub">{{ t('search_mode_kb') }}</span>
      <div class="tool-options">
        <label
          v-for="tool in CUSTOM_TOOLS"
          :key="tool"
          :title="toolDescription(tool)"
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
      <span class="toggle-label toggle-label--sub">{{ t('search_mode_specific_label') }}</span>
      <div class="tool-options">
        <label
          v-for="kb in specificKbs"
          :key="kb.id"
          :title="kbDescription(kb)"
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
      <span class="toggle-label toggle-label--sub">{{ t('search_mode_other') }}</span>

        <!-- Web search lives at the very end of the specific KB section -->
        <label
          :title="toolDescription('web_search')"
          :class="{ active: store.customTools.has('web_search'), disabled: store.searchModeLocked }"
        >
          <input
            type="checkbox"
            :checked="store.customTools.has('web_search')"
            :disabled="store.searchModeLocked"
            @change="toggleTool('web_search')"
          />
          {{ toolLabel('web_search') }}
        </label>
        <!-- Sensible Dokumente: per-chat privacy choice. When on, no feedback
             (thumbs up/down or comment) is logged for this chat. -->
        <label
          :class="{ active: store.sensitiveDocs, disabled: store.searchModeLocked }"
          :title="t('sensitive_docs_tip')"
        >
          <input
            type="checkbox"
            :checked="store.sensitiveDocs"
            :disabled="store.searchModeLocked"
            @change="store.setSensitiveDocs(!store.sensitiveDocs)"
          />
          {{ t('sensitive_docs_label') }}
        </label>
      </div>
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
