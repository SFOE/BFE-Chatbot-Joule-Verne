<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

interface SpecificKb {
  id: string
  // Stable config slug (e.g. "gebaeudeprogramm", "interne-weisungen"); used to
  // resolve per-KB help texts. The id is the dynamic Bedrock KB id.
  slug?: string
  names: { de: string; fr: string; it: string; en: string }
}

const { t, te, locale } = useI18n()

// Search modes shown in the "How the assistant searches" section.
const searchModes = [
  { key: 'search_mode_kb', body: 'help_mode_kb_body' },
  { key: 'search_mode_web', body: 'help_mode_web_body' },
  { key: 'search_mode_specific_label', body: 'help_mode_custom_body' },
] as const

// URLs for the external sources referenced in the tool descriptions. The
// source names inside each description are rendered as real links via the
// <i18n-t> component interpolation (see template), so the sentence stays
// translatable while the linked words point at the correct site.
const sourceUrls = {
  bfe: 'https://www.bfe.admin.ch',
  energieschweiz: 'https://www.energieschweiz.ch',
  medienmitteilungen: 'https://www.bfe.admin.ch/de/newnsb',
  fedlex: 'https://www.fedlex.admin.ch',
  parlament: 'https://www.parlament.ch/de/ratsbetrieb/curia-vista',
  aramis: 'https://www.aramis.admin.ch',
  gebaeudeprogramm: 'https://www.dasgebaeudeprogramm.ch',
  i14y: 'https://www.i14y.admin.ch',
} as const

// Source placeholders that a KB description may reference (e.g. {gebaeudeprogramm},
// {i14y}). Each is rendered as a real link via <i18n-t>; a description only
// consumes the placeholders it actually mentions, so passing all of them is safe.
const SOURCE_KEYS = Object.keys(sourceUrls) as (keyof typeof sourceUrls)[]

// Specific (personal/group) KBs actually available on the backend. Fetched from
// the same endpoint the chat mode selector uses, so the help list always
// reflects the configured KBs instead of a hardcoded set.
const specificKbs = ref<SpecificKb[]>([])

onMounted(async () => {
  try {
    const response = await fetch('/v1/kbs/specific')
    if (response.ok) {
      specificKbs.value = await response.json()
    }
  } catch {
    // Silently ignore — specific KBs are optional.
  }
})

// Localized display name of a KB, mirroring the chat mode selector.
function kbName(kb: SpecificKb): string {
  const loc = locale.value as keyof SpecificKb['names']
  return kb.names[loc] || kb.names.de || kb.id
}

// Normalise the backend slug to the underscore style used by locale keys
// (help_kb_<slug>_desc), e.g. "interne-weisungen" -> "interne_weisungen".
function kbKeySlug(kb: SpecificKb): string {
  return (kb.slug ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

// Translation key for a KB's description, or '' when none exists.
function kbDescKey(kb: SpecificKb): string {
  const slug = kbKeySlug(kb)
  if (!slug) return ''
  const key = `help_kb_${slug}_desc`
  return te(key) ? key : ''
}
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
            <template #medienmitteilungen>
              <a :href="sourceUrls.medienmitteilungen" target="_blank" rel="noopener noreferrer">{{ t('help_source_medienmitteilungen') }}</a>
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
      </ul>
      <p v-if="specificKbs.length" class="help-tools-intro">{{ t('help_specific_kbs_intro') }}</p>
      <ul v-if="specificKbs.length" class="help-tools">
        <li v-for="kb in specificKbs" :key="kb.id">
          <strong>{{ kbName(kb) }}</strong>
          <template v-if="kbDescKey(kb)">
            {{ ': ' }}
            <i18n-t :keypath="kbDescKey(kb)" scope="global" tag="span">
              <template v-for="src in SOURCE_KEYS" :key="src" #[src]>
                <a :href="sourceUrls[src]" target="_blank" rel="noopener noreferrer">{{ t(`help_source_${src}`) }}</a>
              </template>
            </i18n-t>
          </template>
        </li>
      </ul>
            <p class="help-tools-intro">{{ t('help_other_intro') }}</p>
      <ul class="help-tools">
        <li>
          <strong>{{ t('tool_web_search') }}</strong>{{ ': ' }}{{ t('help_tool_web_search_desc') }}
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
