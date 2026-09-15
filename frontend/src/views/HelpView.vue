<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// Search modes shown in the "How the assistant searches" section.
const searchModes = [
  { key: 'help_mode_kb_title', body: 'help_mode_kb_body' },
  { key: 'help_mode_custom_title', body: 'help_mode_custom_body' },
] as const

// URLs for the external sources referenced in the tool descriptions. The
// source names inside each description are rendered as real links via the
// <i18n-t> component interpolation (see template), so the sentence stays
// translatable while the linked words point at the correct site.
const sourceUrls = {
  bfe: 'https://www.bfe.admin.ch',
  energieschweiz: 'https://www.energieschweiz.ch',
  fedlex: 'https://www.fedlex.admin.ch',
  parlament: 'https://www.parlament.ch/de/ratsbetrieb/curia-vista',
  aramis: 'https://www.aramis.admin.ch',
  gebaeudeprogramm: 'https://www.dasgebaeudeprogramm.ch',
  i14y: 'https://www.i14y.admin.ch',
} as const
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
        <li>
          <strong>{{ t('tool_kb_documents') }}</strong>{{ ': ' }}{{ t('help_tool_kb_documents_desc') }}
        </li>
        <li>
          <strong>{{ t('tool_kb_website') }}</strong>{{ ': ' }}
          <i18n-t keypath="help_tool_kb_website_desc" scope="global" tag="span">
            <template #bfe>
              <a :href="sourceUrls.bfe" target="_blank" rel="noopener noreferrer">{{ t('help_source_bfe') }}</a>
            </template>
            <template #energieschweiz>
              <a :href="sourceUrls.energieschweiz" target="_blank" rel="noopener noreferrer">{{ t('help_source_energieschweiz') }}</a>
            </template>
          </i18n-t>
        </li>
        <li>
          <strong>{{ t('tool_kb_legislation') }}</strong>{{ ': ' }}
          <i18n-t keypath="help_tool_kb_legislation_desc" scope="global" tag="span">
            <template #fedlex>
              <a :href="sourceUrls.fedlex" target="_blank" rel="noopener noreferrer">{{ t('help_source_fedlex') }}</a>
            </template>
            <template #parlament>
              <a :href="sourceUrls.parlament" target="_blank" rel="noopener noreferrer">{{ t('help_source_parlament') }}</a>
            </template>
          </i18n-t>
        </li>
        <li>
          <strong>{{ t('tool_aramis') }}</strong>{{ ': ' }}
          <i18n-t keypath="help_tool_aramis_desc" scope="global" tag="span">
            <template #aramis>
              <a :href="sourceUrls.aramis" target="_blank" rel="noopener noreferrer">{{ t('help_source_aramis') }}</a>
            </template>
          </i18n-t>
        </li>
        <li>
          <strong>{{ t('tool_web_search') }}</strong>{{ ': ' }}{{ t('help_tool_web_search_desc') }}
        </li>
      </ul>
      <p class="help-tools-intro">{{ t('help_specific_kbs_intro') }}</p>
      <ul class="help-tools">
        <li>
          <strong>{{ t('help_kb_gebaeudeprogramm') }}</strong>{{ ': ' }}
          <i18n-t keypath="help_kb_gebaeudeprogramm_desc" scope="global" tag="span">
            <template #gebaeudeprogramm>
              <a :href="sourceUrls.gebaeudeprogramm" target="_blank" rel="noopener noreferrer">{{ t('help_source_gebaeudeprogramm') }}</a>
            </template>
          </i18n-t>
        </li>
        <li>
          <strong>{{ t('help_kb_medienarchiv') }}</strong>{{ ': ' }}{{ t('help_kb_medienarchiv_desc') }}
        </li>
        <li>
          <strong>{{ t('help_kb_interne_weisungen') }}</strong>{{ ': ' }}{{ t('help_kb_interne_weisungen_desc') }}
        </li>
        <li>
          <strong>{{ t('help_kb_i14y') }}</strong>{{ ': ' }}
          <i18n-t keypath="help_kb_i14y_desc" scope="global" tag="span">
            <template #i14y>
              <a :href="sourceUrls.i14y" target="_blank" rel="noopener noreferrer">{{ t('help_source_i14y') }}</a>
            </template>
          </i18n-t>
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
