import { createI18n } from 'vue-i18n'
import { mount, type MountingOptions } from '@vue/test-utils'
import en from '../i18n/locales/en.json'

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
})

export function mountWithI18n<T>(
  component: T,
  options?: MountingOptions<T>,
) {
  return mount(component as any, {
    ...options,
    global: {
      ...options?.global,
      plugins: [...(options?.global?.plugins ?? []), i18n],
    },
  })
}
