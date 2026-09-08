<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// Search modes shown in the "How the assistant searches" section.
const searchModes = [
  { key: 'help_mode_kb_title', body: 'help_mode_kb_body' },
  { key: 'help_mode_custom_title', body: 'help_mode_custom_body' },
] as const

// Tools available in "Own choice" mode. Keys mirror the labels used in
// SearchModeToggle.vue so the help text stays consistent with the UI.
const tools = [
  'tool_kb_documents',
  'tool_kb_website',
  'tool_kb_legislation',
  'tool_aramis',
  'tool_web_search',
  'tool_code_interpreter',
  'tool_mcp_i14y',
] as const
</script>

<template>
  <div class="help-page">
    <h2>{{ t('help_title') }}</h2>
    <p class="help-intro">{{ t('help_intro') }}</p>

    <section class="help-section">
      <h3>{{ t('help_ask_title') }}</h3>
      <p>{{ t('help_ask_body') }}</p>
    </section>

    <section class="help-section">
      <h3>{{ t('help_modes_title') }}</h3>
      <div v-for="mode in searchModes" :key="mode.key" class="help-mode">
        <h4>{{ t(mode.key) }}</h4>
        <p>{{ t(mode.body) }}</p>
      </div>
      <p class="help-tools-intro">{{ t('help_tools_intro') }}</p>
      <ul class="help-tools">
        <li v-for="tool in tools" :key="tool">
          <strong>{{ t(tool) }}</strong>{{ ': ' }}{{ t(`help_${tool}_desc`) }}
        </li>
      </ul>
    </section>

    <section class="help-section">
      <h3>{{ t('help_features_title') }}</h3>
      <ul>
        <li>{{ t('help_feature_sources') }}</li>
        <li>{{ t('help_feature_upload') }}</li>
        <li>{{ t('help_feature_language') }}</li>
        <li>{{ t('help_feature_feedback') }}</li>
        <li>{{ t('help_feature_clear') }}</li>
      </ul>
    </section>

    <section class="help-section">
      <h3>{{ t('help_notes_title') }}</h3>
      <ul>
        <li>{{ t('help_note_accuracy') }}</li>
        <li>{{ t('help_note_websearch') }}</li>
        <li>{{ t('help_note_privacy') }}</li>
      </ul>
    </section>

    <router-link to="/" class="back-link">← {{ t('back_to_chat') }}</router-link>
  </div>
</template>
