<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <header class="header">
    <div class="header-content">
      <img src="/bundesamt_logo.jpeg" alt="BFE Logo" class="header-logo" />
      <h1 class="header-title">{{ t('app_title') }}</h1>
    </div>
  </header>
</template>
