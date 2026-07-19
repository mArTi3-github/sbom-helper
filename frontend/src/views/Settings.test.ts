import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import { resetThemeState } from '../composables/useTheme'
import Settings from './Settings.vue'
import type { SettingsResponse } from '../types/api'

const defaultSettings: SettingsResponse = {
  validate_db_urls: false,
  validate_sbom_refs: false,
  sbom_multiple_vcs_behavior: 'keep-first',
  url_validation_timeout: 5,
  revalidation_cooldown_hours: 24,
  retry_max_attempts: 3,
  retry_base_cooldown_seconds: 5,
  log_level: 'INFO',
  librariesio_enabled: false,
  ecosystems_enabled: false,
  ecosystems_max_requests_per_second: 2,
  batch_semaphore_limit: 10,
  connectivity_url: 'https://github.com',
  connectivity_timeout: 2,
  json_indent: 4,
  job_ttl_hours: 24,
  token_set: { librariesio_api_key: false, ecosystems_api_key: false },
}

const successUpdate = vi.fn().mockResolvedValue(defaultSettings)
const getSettingsMock = vi.fn().mockResolvedValue(defaultSettings)

vi.mock('../api/settings', () => ({
  getSettings: () => getSettingsMock(),
  updateSettings: (body: unknown) => successUpdate(body),
}))

async function flush(ms = 0) {
  if (ms > 0) vi.advanceTimersByTime(ms)
  await flushPromises()
}

function mountSettings(): VueWrapper {
  return mountWithI18n(Settings)
}

describe('Settings.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    successUpdate.mockResolvedValue(defaultSettings)
    getSettingsMock.mockResolvedValue(defaultSettings)
    localStorage.clear()
    resetThemeState()
    document.documentElement.classList.remove('light-theme')
  })

  it('renders the loaded settings', async () => {
    const wrapper = mountSettings()
    await flushPromises()
    expect(wrapper.find('.loading').exists()).toBe(false)
    expect(wrapper.findAll('input[type="number"]').length).toBeGreaterThan(0)
    expect(wrapper.findAll('input[type="password"]').length).toBe(2)
    expect(getSettingsMock).toHaveBeenCalledTimes(1)
  })

  it('auto-saves toggle change after debounce', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      expect(checkboxes.length).toBeGreaterThanOrEqual(1)
      await checkboxes[0].setValue(true)
      await flush()
      expect(successUpdate).not.toHaveBeenCalled()

      await flush(500)
      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ validate_db_urls: true })
    } finally {
      vi.useRealTimers()
    }
  })

  it('coalesces rapid toggle changes into a single PATCH', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      await checkboxes[0].setValue(true)
      await flush()
      await checkboxes[0].setValue(false)
      await flush()
      await checkboxes[0].setValue(true)
      await flush(500)

      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ validate_db_urls: true })
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows success toast after a successful PATCH', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      await checkboxes[0].setValue(true)
      await flush(500)
      await flushPromises()

      const toast = wrapper.find('.toast')
      expect(toast.exists()).toBe(true)
      expect(toast.classes()).toContain('toast-ok')
      expect(toast.text()).toBe('Settings saved')
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows error toast when PATCH fails', async () => {
    vi.useFakeTimers()
    try {
      successUpdate.mockRejectedValueOnce(new Error('boom'))
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      await checkboxes[0].setValue(true)
      await flush(500)
      await flushPromises()

      const toast = wrapper.find('.toast')
      expect(toast.exists()).toBe(true)
      expect(toast.classes()).toContain('toast-err')
      expect(toast.text()).toBe('Failed to save: boom')
    } finally {
      vi.useRealTimers()
    }
  })

  it('renders theme selector and switches theme', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const themeSelect = wrapper.findAll('select').find((s) => {
      const options = s.findAll('option')
      return options.length === 2 &&
        options.some((o) => o.text() === 'Dark') &&
        options.some((o) => o.text() === 'Light')
    })
    expect(themeSelect).toBeDefined()

    await themeSelect!.setValue('light')
    await flushPromises()
    expect(document.documentElement.classList.contains('light-theme')).toBe(true)
    expect(localStorage.getItem('theme')).toBe('light')

    await themeSelect!.setValue('dark')
    await flushPromises()
    expect(document.documentElement.classList.contains('light-theme')).toBe(false)
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})