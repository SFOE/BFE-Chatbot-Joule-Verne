<template>
  <header class="app-header">
    <div class="top-header-box">
      <div class="top-header-inner">
        <LanguageSwitcherComponent />
      </div>
    </div>

    <div class="bottom-header-box">
      <div class="bottom-header-inner">
        <div class="logo-title-group">
          <img
            class="logo responsive-logo"
            alt="Swiss Logo"
            src="@/assets/logo.png"
            width="200"
            height="68"
            fetchpriority="high"
          />
          <div class="title-block">
            <h1 class="title">{{ t('header_title') }}</h1>
            <p class="app-title">{{ t('app_title') }}</p>
          </div>
        </div>
      </div>
    </div>

    <div class="header-line"></div>
  </header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import LanguageSwitcherComponent from './LanguageSwitcherComponent.vue'

const { t } = useI18n()
</script>

<style scoped>
.app-header {
  width: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg);
}

.top-header-box {
  width: 100%;
  height: 50px;
  background-color: var(--color-primary);
  display: flex;
  align-items: center;
}

.top-header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  width: 100%;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.bottom-header-box {
  width: 100%;
  background-color: var(--color-bg);
}

.bottom-header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem 20px 1.75rem 20px;
  width: 100%;
  display: flex;
  align-items: flex-start;
}

.logo-title-group {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.logo {
  display: block;
  height: 68px;
  width: auto;
  flex-shrink: 0;
}

.responsive-logo {
  content: url('@/assets/logo.png');
}

.title {
  margin: 0;
  font-size: 16px;
  line-height: 1.2;
}

.title-block {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-self: stretch;
  gap: 0;
}

.app-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--color-text, #333);
}

.divider {
  width: 1px;
  background-color: var(--color-separator);
  align-self: stretch;
}

.header-line {
  width: 100%;
  height: 1px;
  background-color: var(--color-separator);
}

@media (max-width: 768px) {
  .responsive-logo {
    content: url('@/assets/swiss_mobile.svg');
    height: 20px;
    padding-left: 10px;
  }

  .bottom-header-inner {
    max-height: 50px;
    vertical-align: center;
  }

  .logo-title-group {
    flex-direction: row;
    align-items: center;
    gap: 12px;
  }

  .divider {
    display: none;
  }

  .title {
    font-size: 13px;
  }

  .app-title {
    font-size: 18px;
  }
}

@media (max-width: 480px) {
  .title {
    font-size: 12px;
  }

  .app-title {
    font-size: 16px;
  }
}
</style>
