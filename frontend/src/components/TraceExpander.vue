<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TraceStep } from '@/types/chat'

const { t } = useI18n()

defineProps<{
  steps: TraceStep[]
}>()

const expanded = ref(false)
</script>

<template>
  <details class="trace-expander" :open="expanded" @toggle="expanded = ($event.target as HTMLDetailsElement).open">
    <summary>🔎 {{ t('trace_title') }}</summary>
    <div class="trace-steps">
      <div v-for="(step, i) in steps" :key="i" class="trace-step">
        <strong>{{ step.label }}</strong>
        <pre v-if="step.detail" class="trace-detail">{{ step.detail }}</pre>
      </div>
    </div>
  </details>
</template>
