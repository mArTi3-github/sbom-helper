import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import ru from './locales/ru.json'

function ruPluralization(n: number): number {
  if (n % 10 === 1 && n % 100 !== 11) return 0
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return 1
  return 2
}

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, ru },
  pluralRules: {
    ru: ruPluralization,
  },
})
