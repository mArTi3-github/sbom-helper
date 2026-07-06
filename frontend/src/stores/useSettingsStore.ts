import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSettings, updateSettings } from '../api/settings'
import type { SettingsUpdate } from '../types/api'

export const useSettingsStore = defineStore('settings', () => {
  const validateDbUrls = ref(false)
  const validateSbomRefs = ref(false)
  const urlValidationTimeout = ref(5)
  const revalidationCooldownHours = ref(24)
  const retryMaxAttempts = ref(3)
  const retryBaseCooldownSeconds = ref(5)
  const logLevel = ref('INFO')
  const librariesioEnabled = ref(false)
  const ecosystemsEnabled = ref(false)
  const ecosystemsMaxRequestsPerSecond = ref(2)
  const batchSemaphoreLimit = ref(10)
  const connectivityUrl = ref('https://github.com')
  const connectivityTimeout = ref(2)
  const jsonIndent = ref(4)
  const tokenSet = ref({ github_token: false, librariesio_api_key: false, ecosystems_api_key: false })
  const githubToken = ref('')
  const librariesioKey = ref('')
  const ecosystemsKey = ref('')
  const loading = ref(true)

  const hasAnyToken = computed(() =>
    tokenSet.value.github_token || tokenSet.value.librariesio_api_key || tokenSet.value.ecosystems_api_key
  )

  async function load() {
    try {
      const data = await getSettings()
      validateDbUrls.value = data.validate_db_urls
      validateSbomRefs.value = data.validate_sbom_refs
      urlValidationTimeout.value = data.url_validation_timeout
      revalidationCooldownHours.value = data.revalidation_cooldown_hours
      retryMaxAttempts.value = data.retry_max_attempts
      retryBaseCooldownSeconds.value = data.retry_base_cooldown_seconds
      logLevel.value = data.log_level
      librariesioEnabled.value = data.librariesio_enabled
      ecosystemsEnabled.value = data.ecosystems_enabled
      ecosystemsMaxRequestsPerSecond.value = data.ecosystems_max_requests_per_second
      batchSemaphoreLimit.value = data.batch_semaphore_limit
      connectivityUrl.value = data.connectivity_url
      connectivityTimeout.value = data.connectivity_timeout
      jsonIndent.value = data.json_indent
      tokenSet.value = data.token_set
    } catch {
      throw new Error('Failed to load settings')
    }
  }

  async function save(partial: SettingsUpdate) {
    const data = await updateSettings(partial)
    tokenSet.value = data.token_set
    if ('github_token' in partial) githubToken.value = ''
    if ('librariesio_api_key' in partial) librariesioKey.value = ''
    if ('ecosystems_api_key' in partial) ecosystemsKey.value = ''
  }

  async function clearToken(field: 'github_token' | 'librariesio_api_key' | 'ecosystems_api_key') {
    await updateSettings({ [field]: null } as SettingsUpdate)
  }

  return {
    validateDbUrls, validateSbomRefs, urlValidationTimeout, revalidationCooldownHours,
    retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
    librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
    batchSemaphoreLimit, connectivityUrl, connectivityTimeout, jsonIndent,
    tokenSet, githubToken, librariesioKey, ecosystemsKey, loading,
    hasAnyToken, load, save, clearToken,
  }
})
