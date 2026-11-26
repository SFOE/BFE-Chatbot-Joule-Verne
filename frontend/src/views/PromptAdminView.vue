<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { backendHttp } from '@/services/http'

interface PromptItem {
  key: string
  label: string
  group: 'general' | 'capability'
  default: string
  override: string | null
}

interface PromptVersion {
  version_id: string
  saved_at: string
  size: number
}

const { t, locale } = useI18n()

const loading = ref(true)
const denied = ref(false)
const loadError = ref(false)
const defaultsAvailable = ref(true)
const maxLength = ref(60000)
const prompts = ref<PromptItem[]>([])
const selectedKey = ref('')
const text = ref('')

const saving = ref(false)
const status = ref<'saved' | 'error' | 'unchanged' | 'version_loaded' | 'version_error' | ''>('')

const versions = ref<PromptVersion[]>([])
const versionsLoading = ref(false)

const selected = computed(() => prompts.value.find((p) => p.key === selectedKey.value) ?? null)
// The text currently active for the selected part (override, else default).
const activeText = computed(() => selected.value?.override ?? selected.value?.default ?? '')
const dirty = computed(() => selected.value !== null && text.value !== activeText.value)
const isCustom = computed(() => selected.value?.override != null)
const generalPrompts = computed(() => prompts.value.filter((p) => p.group === 'general'))
const capabilityPrompts = computed(() => prompts.value.filter((p) => p.group !== 'general'))

function selectKey(key: string) {
  selectedKey.value = key
  status.value = ''
  text.value = activeText.value
  loadVersions()
}

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const { data } = await backendHttp.get<{
      prompts: PromptItem[]
      max_length: number
      defaults_available: boolean
    }>('v1/admin/prompts')
    prompts.value = data.prompts
    maxLength.value = data.max_length
    defaultsAvailable.value = data.defaults_available
    if (prompts.value.length) selectKey(selectedKey.value || prompts.value[0].key)
  } catch (e: unknown) {
    const code = (e as { response?: { status?: number } }).response?.status
    if (code === 403) denied.value = true
    else loadError.value = true
  } finally {
    loading.value = false
  }
}

function onSelectChange(event: Event) {
  const el = event.target as HTMLSelectElement
  if (dirty.value && !window.confirm(t('prompt_admin_discard_confirm'))) {
    el.value = selectedKey.value
    return
  }
  selectKey(el.value)
}

async function loadVersions() {
  const key = selectedKey.value
  if (!key) return
  versionsLoading.value = true
  try {
    const { data } = await backendHttp.get<{ versions: PromptVersion[] }>(
      `v1/admin/prompts/${key}/versions`,
    )
    if (key === selectedKey.value) versions.value = data.versions
  } catch {
    if (key === selectedKey.value) versions.value = []
  } finally {
    versionsLoading.value = false
  }
}

async function persist(newText: string) {
  const item = selected.value
  if (!item) return
  saving.value = true
  status.value = ''
  try {
    // Text equal to the built-in default is stored as "no override".
    const body = newText.trim() === item.default.trim() ? '' : newText
    const { data } = await backendHttp.put<{ override: string | null; version_id: string | null }>(
      `v1/admin/prompts/${item.key}`,
      { text: body },
    )
    item.override = data.override
    text.value = activeText.value
    status.value = data.version_id ? 'saved' : 'unchanged'
    await loadVersions()
  } catch {
    status.value = 'error'
  } finally {
    saving.value = false
  }
}

function save() {
  return persist(text.value)
}

function resetToDefault() {
  if (!selected.value || !window.confirm(t('prompt_admin_reset_confirm'))) return
  return persist('')
}

async function loadVersion(versionId: string) {
  const item = selected.value
  if (!item) return
  if (dirty.value && !window.confirm(t('prompt_admin_discard_confirm'))) return
  try {
    const { data } = await backendHttp.get<{ text: string }>(
      `v1/admin/prompts/${item.key}/versions/${versionId}`,
    )
    // An empty version was a reset to default.
    text.value = data.text || item.default
    status.value = 'version_loaded'
  } catch {
    status.value = 'version_error'
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(locale.value)
}

onMounted(load)
</script>

<template>
  <div class="prompt-admin">
    <h2>{{ t('prompt_admin_title') }}</h2>

    <p v-if="loading" class="prompt-hint">…</p>
    <p v-else-if="denied" class="doc-error" role="alert">{{ t('prompt_admin_denied') }}</p>
    <p v-else-if="loadError" class="doc-error" role="alert">{{ t('prompt_admin_load_error') }}</p>

    <template v-else>
      <p class="prompt-hint">{{ t('prompt_admin_intro') }}</p>
      <p v-if="!defaultsAvailable" class="doc-error" role="alert">
        {{ t('prompt_admin_no_defaults') }}
      </p>

      <div class="prompt-select-row">
        <label for="prompt-select" class="prompt-label">{{ t('prompt_admin_select') }}</label>
        <select
          id="prompt-select"
          class="prompt-select"
          :value="selectedKey"
          @change="onSelectChange"
        >
          <optgroup :label="t('prompt_admin_group_general')">
            <option v-for="p in generalPrompts" :key="p.key" :value="p.key">
              {{ p.label }}{{ p.override != null ? ' *' : '' }}
            </option>
          </optgroup>
          <optgroup :label="t('prompt_admin_group_capability')">
            <option v-for="p in capabilityPrompts" :key="p.key" :value="p.key">
              {{ p.label }}{{ p.override != null ? ' *' : '' }}
            </option>
          </optgroup>
        </select>
        <span v-if="selected" class="prompt-badge">
          {{ isCustom ? t('prompt_admin_status_custom') : t('prompt_admin_status_default') }}
        </span>
      </div>

      <template v-if="selected">
        <textarea
          v-model="text"
          class="prompt-textarea"
          rows="24"
          spellcheck="false"
          :maxlength="maxLength"
          :aria-label="selected.label"
          @input="status = ''"
        ></textarea>

        <div class="prompt-actions">
          <button
            type="button"
            class="file-select-btn"
            :disabled="saving || !dirty"
            @click="save"
          >
            {{ t('prompt_admin_save') }}
          </button>
          <button
            type="button"
            class="file-select-btn"
            :disabled="saving || !isCustom"
            @click="resetToDefault"
          >
            {{ t('prompt_admin_reset') }}
          </button>
          <span class="prompt-hint">{{ text.length }} / {{ maxLength }} {{ t('prompt_admin_chars') }}</span>
          <span v-if="status === 'saved'" class="doc-success" role="status">
            ✅ {{ t('prompt_admin_saved') }}
          </span>
          <span v-else-if="status === 'unchanged'" class="prompt-hint" role="status">
            {{ t('prompt_admin_unchanged') }}
          </span>
          <span v-else-if="status === 'version_loaded'" class="prompt-hint" role="status">
            {{ t('prompt_admin_version_loaded') }}
          </span>
          <span v-else-if="status === 'error'" class="doc-error" role="alert">
            ❌ {{ t('prompt_admin_save_error') }}
          </span>
          <span v-else-if="status === 'version_error'" class="doc-error" role="alert">
            ❌ {{ t('prompt_admin_version_error') }}
          </span>
        </div>

        <section class="prompt-versions">
          <h3>{{ t('prompt_admin_versions') }}</h3>
          <p v-if="versionsLoading" class="prompt-hint">…</p>
          <p v-else-if="!versions.length" class="prompt-hint">
            {{ t('prompt_admin_versions_empty') }}
          </p>
          <ul v-else class="prompt-version-list">
            <li v-for="(v, i) in versions" :key="v.version_id">
              <span>{{ formatDate(v.saved_at) }}</span>
              <span class="prompt-hint">
                {{ v.size === 0 ? t('prompt_admin_version_reset') : `${v.size} B` }}
              </span>
              <span v-if="i === 0 && isCustom" class="prompt-badge">
                {{ t('prompt_admin_status_custom') }}
              </span>
              <button
                type="button"
                class="file-select-btn"
                @click="loadVersion(v.version_id)"
              >
                {{ t('prompt_admin_version_load') }}
              </button>
            </li>
          </ul>
        </section>
      </template>
    </template>
  </div>
</template>

<style scoped>
.prompt-admin {
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  padding: 1.5rem;
  overflow-y: auto;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.prompt-hint {
  font-size: 0.85em;
  color: var(--color-muted);
}

.prompt-select-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.prompt-label {
  font-weight: 600;
}

.prompt-select {
  padding: 0.5rem;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  min-width: 280px;
  max-width: 100%;
}

.prompt-badge {
  padding: 0 0.4rem;
  font-size: 0.75em;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-muted);
  white-space: nowrap;
}

.prompt-textarea {
  width: 100%;
  padding: 0.75rem;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.85rem;
  line-height: 1.45;
  resize: vertical;
}

.prompt-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.prompt-versions h3 {
  margin: 0.75rem 0 0.5rem;
}

.prompt-version-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.prompt-version-list li {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--color-border);
}
</style>
