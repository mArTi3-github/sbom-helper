import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSettings, updateSettings } from '../api/settings'
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
  const depsdevEnabled = ref(false)
  const apkEnabled = ref(false)
  const ecosystemsEnabled = ref(false)
  const ecosystemsMaxRequestsPerSecond = ref(2)
  const batchSemaphoreLimit = ref(10)
  const jobTtlHours = ref(24)
  const connectivityUrl = ref('https://github.com')
  const connectivityTimeout = ref(2)
  const jsonIndent = ref(4)
  const llmEnabled = ref(false)
  const llmBaseUrl = ref('')
  const llmModel = ref('')
  const llmAttemptsCount = ref(2)
  const llmTimeout = ref(60)
  const tokenSet = ref({ librariesio_api_key: false, ecosystems_api_key: false, llm_resolver_api_key: false })
  const librariesioKey = ref('')
  const ecosystemsKey = ref('')
  const llmApiKey = ref('')
  const loading = ref(true)

  const hasAnyToken = computed(() =>
    tokenSet.value.librariesio_api_key || tokenSet.value.ecosystems_api_key || tokenSet.value.llm_resolver_api_key
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
      depsdevEnabled.value = data.depsdev_enabled
      apkEnabled.value = data.apk_resolver_enabled
      ecosystemsEnabled.value = data.ecosystems_enabled
      ecosystemsMaxRequestsPerSecond.value = data.ecosystems_max_requests_per_second
      batchSemaphoreLimit.value = data.batch_semaphore_limit
      jobTtlHours.value = data.job_ttl_hours
      connectivityUrl.value = data.connectivity_url
      connectivityTimeout.value = data.connectivity_timeout
      jsonIndent.value = data.json_indent
      llmEnabled.value = data.llm_resolver_enabled
      llmBaseUrl.value = data.llm_resolver_base_url ?? ''
      llmModel.value = data.llm_resolver_model ?? ''
      llmAttemptsCount.value = data.llm_resolver_attempts_count
      llmTimeout.value = data.llm_resolver_timeout
      tokenSet.value = data.token_set
    } catch {
      throw new Error('Failed to load settings')
    }
  }

  async function save(partial: SettingsUpdate) {
    const data = await updateSettings(partial)
    tokenSet.value = data.token_set
    if ('librariesio_api_key' in partial) librariesioKey.value = ''
    if ('ecosystems_api_key' in partial) ecosystemsKey.value = ''
    if ('llm_resolver_api_key' in partial) llmApiKey.value = ''
  }

  async function clearToken(field: 'librariesio_api_key' | 'ecosystems_api_key' | 'llm_resolver_api_key') {
    await updateSettings({ [field]: null } as SettingsUpdate)
  }

  return {
    validateDbUrls, validateSbomRefs, sbomMultipleVcsBehavior, urlValidationTimeout, revalidationCooldownHours,
    retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
    librariesioEnabled, depsdevEnabled, apkEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
    batchSemaphoreLimit, jobTtlHours, connectivityUrl, connectivityTimeout, jsonIndent,
    llmEnabled, llmBaseUrl, llmModel, llmAttemptsCount, llmTimeout,
    tokenSet, librariesioKey, ecosystemsKey, llmApiKey, loading,
    hasAnyToken, load, save, clearToken,
  }
})
