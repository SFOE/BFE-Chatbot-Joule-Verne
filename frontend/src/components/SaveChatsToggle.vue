<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'

const { t } = useI18n()
const store = useChatStore()

onMounted(() => {
  store.loadSavePreference()
})

function onToggle(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  store.updateSavePreference(checked)
}
</script>

<template>
  <div class="save-chats-toggle">
    <label class="save-chats-toggle__row">
      <input
        type="checkbox"
        :checked="store.saveChatsEnabled"
        @change="onToggle"
      />
      <span>{{ t('save_chats_label') }}</span>
    </label>
    <p class="save-chats-toggle__hint">{{ t('save_chats_hint') }}</p>
  </div>
</template>

<style scoped>
.save-chats-toggle__row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9rem;
  cursor: pointer;
}

.save-chats-toggle__hint {
  margin-top: 0.35rem;
  font-size: 0.75rem;
  opacity: 0.7;
  line-height: 1.3;
}
</style>
