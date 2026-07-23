import { createI18n } from 'vue-i18n'
import de from '@/locales/de.json'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'de',
  fallbackWarn: false,
  missingWarn: false,
  messages: { de },
})

/**
 * Lazily load a locale and set it as active.
 * Adding FR/IT/EN later: just create the JSON file and call this.
 */
export async function setLocale(locale: string) {
  if (!(i18n.global.availableLocales as string[]).includes(locale)) {
    const messages = await import(`./locales/${locale}.json`)
    i18n.global.setLocaleMessage(locale, messages.default)
  }
  i18n.global.locale.value = locale as 'de'
  document.documentElement.lang = locale
  document.title = i18n.global.t('page_title')
}

export default i18n
