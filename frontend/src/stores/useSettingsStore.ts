import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSettings, updateSettings, checkGithubToken as checkGithubTokenApi } from '../api/settings'
import type { SettingsUpdate } from '../types/api'

export const useSettingsStore = defineStore('settings', () => {
  const validateDbUrls = ref(false)
  const validateSbomRefs = ref(false)
  const sbomMultipleVcsBehavior = ref('keep-first')
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
  const language = ref('en')
  const tokenSet = ref({ github_token: false, librariesio_api_key: false, ecosystems_api_key: false })
  const githubTokenValidity = ref<'valid' | 'invalid' | null>(null)
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
      sbomMultipleVcsBehavior.value = data.sbom_multiple_vcs_behavior
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
      language.value = data.language
      tokenSet.value = data.token_set
    } catch {
      throw new Error('Failed to load settings')
    }
  }

  async function save(partial: SettingsUpdate) {
    const data = await updateSettings(partial)
    tokenSet.value = data.token_set
    if ('github_token' in partial) {
      githubToken.value = ''
      githubTokenValidity.value = 'valid'
    }
    if ('librariesio_api_key' in partial) librariesioKey.value = ''
    if ('ecosystems_api_key' in partial) ecosystemsKey.value = ''
  }

  async function clearToken(field: 'github_token' | 'librariesio_api_key' | 'ecosystems_api_key') {
    await updateSettings({ [field]: null } as SettingsUpdate)
    if (field === 'github_token') githubTokenValidity.value = null
  }

  async function checkGithubToken() {
    const result = await checkGithubTokenApi()
    githubTokenValidity.value = result.status
  }

  return {
    validateDbUrls, validateSbomRefs, sbomMultipleVcsBehavior, urlValidationTimeout, revalidationCooldownHours,
    retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
    librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
    batchSemaphoreLimit, connectivityUrl, connectivityTimeout, jsonIndent,
    language,
    tokenSet, githubToken, librariesioKey, ecosystemsKey, loading,
    githubTokenValidity,
    hasAnyToken, load, save, clearToken, checkGithubToken,
  }
})
