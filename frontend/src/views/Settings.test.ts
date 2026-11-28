import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import { resetThemeState } from '../composables/useTheme'
import Settings from './Settings.vue'
import { useSettingsStore } from '../stores/useSettingsStore'
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
  depsdev_enabled: true,
  apk_resolver_enabled: false,
  ecosystems_enabled: false,
  ecosystems_max_requests_per_second: 2,
  batch_semaphore_limit: 10,
  batch_max_items: 100,
  connectivity_url: 'https://github.com',
  connectivity_timeout: 2,
  json_indent: 4,
  job_ttl_hours: 24,
  llm_resolver_enabled: false,
  llm_resolver_base_url: null,
  llm_resolver_model: null,
  llm_resolver_attempts_count: 2,
  llm_resolver_max_tool_rounds: 3,
  llm_resolver_timeout: 60,
  llm_resolver_verify_ssl: true,
  llm_resolver_ca_bundle: null,
  source_archive_timeout: 30,
  source_archive_concurrency: 5,
  token_set: { librariesio_api_key: false, ecosystems_api_key: false, llm_resolver_api_key: false },
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

function findNumberInputByLabel(wrapper: VueWrapper, label: string) {
  const row = wrapper.findAll('.setting-row').find((item) => item.find('.setting-label').exists() && item.find('.setting-label').text() === label)
  expect(row).toBeDefined()
  return row!.find<HTMLInputElement>('input[type="number"]')
}

function findTextInputByLabel(wrapper: VueWrapper, label: string) {
  const row = wrapper.findAll('.setting-row').find((item) => item.find('.setting-label').exists() && item.find('.setting-label').text() === label)
  expect(row).toBeDefined()
  return row!.find<HTMLInputElement>('input[type="text"]')
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
    expect(wrapper.findAll('input[type="password"]').length).toBe(3)
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

  it('auto-saves batch max items change after debounce', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const numberInputs = wrapper.findAll<HTMLInputElement>('input[type="number"]')
      const maxItemsInput = numberInputs.find((i) => i.element.value === '100')
      expect(maxItemsInput).toBeDefined()
      await maxItemsInput!.setValue(250)
      await flush(500)

      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ batch_max_items: 250 })
    } finally {
      vi.useRealTimers()
    }
  })

  it('loads source archive timeout and concurrency', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const store = useSettingsStore()
    expect(store.sourceArchiveTimeout).toBe(30)
    expect(store.sourceArchiveConcurrency).toBe(5)
    expect(findNumberInputByLabel(wrapper, 'Source archive timeout (seconds)').element.value).toBe('30')
    expect(findNumberInputByLabel(wrapper, 'Source archive concurrency').element.value).toBe('5')
  })

  it('auto-saves source archive timeout change after debounce', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const timeoutInput = findNumberInputByLabel(wrapper, 'Source archive timeout (seconds)')
      await timeoutInput.setValue(45)
      await flush(500)

      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ source_archive_timeout: 45 })
    } finally {
      vi.useRealTimers()
    }
  })

  it('auto-saves source archive concurrency change after debounce', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const concurrencyInput = findNumberInputByLabel(wrapper, 'Source archive concurrency')
      await concurrencyInput.setValue(8)
      await flush(500)

      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ source_archive_concurrency: 8 })
    } finally {
      vi.useRealTimers()
    }
  })

  it('renders and auto-saves LLM TLS controls', async () => {
    vi.useFakeTimers()
    try {
      const store = useSettingsStore()
      const wrapper = mountSettings()
      await flushPromises()
      store.llmEnabled = true
      await flushPromises()

      const caInput = findTextInputByLabel(wrapper, 'CA bundle path (PEM)')
      await caInput.setValue('/etc/ssl/corp-ca.pem')
      await caInput.trigger('blur')
      await flush(500)
      expect(successUpdate).toHaveBeenCalledWith({ llm_resolver_ca_bundle: '/etc/ssl/corp-ca.pem' })

      store.llmEnabled = true
      await flushPromises()

      const verifyRow = wrapper.findAll('.setting-row').find((r) => r.find('.setting-label').exists() && r.find('.setting-label').text() === 'Verify TLS certificate')
      expect(verifyRow).toBeDefined()
      const verifyInput = verifyRow!.find<HTMLInputElement>('input[type="checkbox"]')
      await verifyInput.setValue(false)
      await flush(500)
      expect(successUpdate).toHaveBeenCalledWith({ llm_resolver_verify_ssl: false })
    } finally {
      vi.useRealTimers()
    }
  })

  it('renders and auto-saves LLM max tool rounds', async () => {
    vi.useFakeTimers()
    try {
      const store = useSettingsStore()
      const wrapper = mountSettings()
      await flushPromises()
      store.llmEnabled = true
      await flushPromises()

      const roundsInput = findNumberInputByLabel(wrapper, 'Max search rounds')
      expect(roundsInput.element.value).toBe('3')

      await roundsInput.setValue(5)
      await flush(500)

      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ llm_resolver_max_tool_rounds: 5 })
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