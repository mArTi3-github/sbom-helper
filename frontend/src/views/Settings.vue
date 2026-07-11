<template>
  <div class="settings-page">
    <h1>{{ t('settings.title') }}</h1>
    <p class="subtitle">{{ t('settings.subtitle') }}</p>

    <div v-if="loading" class="loading">
      <span class="spinner"></span>
      {{ t('common.loading') }}
    </div>

    <template v-if="!loading">
      <div class="card">
        <div class="card-title">{{ t('settings.language') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.language') }}</div>
          </div>
          <select
            :value="locale"
            @change="setLanguage"
            class="select-input"
          >
            <option value="en">{{ t('settings.languageEn') }}</option>
            <option value="ru">{{ t('settings.languageRu') }}</option>
          </select>
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.urlValidation.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.urlValidation.validateDbUrls') }}</div>
            <div class="setting-desc">
              {{ t('settings.urlValidation.validateDbUrlsDesc') }}
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="validateDbUrls" @change="debouncedAutoSave({ validate_db_urls: validateDbUrls })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.urlValidation.validateSbomRefs') }}</div>
            <div class="setting-desc">
              {{ t('settings.urlValidation.validateSbomRefsDesc') }}
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="validateSbomRefs" @change="debouncedAutoSave({ validate_sbom_refs: validateSbomRefs })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row" :class="{ 'setting-disabled': !validateSbomRefs }">
          <div>
            <div class="setting-label">{{ t('settings.urlValidation.multipleVcs') }}</div>
            <div class="setting-desc">
              {{ t('settings.urlValidation.multipleVcsDesc') }}
            </div>
          </div>
          <select
            v-model="sbomMultipleVcsBehavior"
            :disabled="!validateSbomRefs"
            @change="debouncedAutoSave({ sbom_multiple_vcs_behavior: sbomMultipleVcsBehavior })"
            class="select-input"
          >
            <option value="keep-first">{{ t('settings.urlValidation.keepFirst') }}</option>
            <option value="keep-all">{{ t('settings.urlValidation.keepAll') }}</option>
          </select>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.urlValidation.timeout') }}</div>
            <div class="setting-desc">
              {{ t('settings.urlValidation.timeoutDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="urlValidationTimeout" min="1" max="60" @change="debouncedAutoSave({ url_validation_timeout: urlValidationTimeout })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.urlValidation.cooldown') }}</div>
            <div class="setting-desc">
              {{ t('settings.urlValidation.cooldownDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="revalidationCooldownHours" min="0" max="720" @change="debouncedAutoSave({ revalidation_cooldown_hours: revalidationCooldownHours })" class="num-input">
        </div>
        <div class="setting-row info-row">
          <div class="setting-desc">
            {{ t('settings.urlValidation.infoText') }}
          </div>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.urlValidation.clearCache') }}</div>
            <div class="setting-desc">
              {{ t('settings.urlValidation.clearCacheDesc') }}
            </div>
          </div>
          <button class="btn btn-secondary" @click="onClearValidationCache">{{ t('settings.urlValidation.clearCacheBtn') }}</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.githubToken.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.githubToken.label') }}</div>
            <div class="setting-desc">
              {{ t('settings.githubToken.desc') }}
            </div>
            <div class="setting-desc link-desc">
              <a href="https://github.com/settings/tokens" target="_blank">{{ t('settings.githubToken.genToken') }}</a>
              {{ t('settings.githubToken.genTokenHint') }}
            </div>
            <div class="setting-desc status-desc">
              {{ t('settings.githubToken.status') }} <span :class="tokenSet.github_token ? 'status-set' : 'status-not-set'">{{ tokenSet.github_token ? t('settings.set') : t('settings.notSet') }}</span>
              <button v-if="tokenSet.github_token" class="btn btn-danger btn-sm" @click="clearToken">{{ t('settings.clearToken') }}</button>
            </div>
            <div v-if="tokenSet.github_token" class="setting-desc validity-desc">
              {{ t('settings.githubToken.validity') }}
              <span v-if="githubTokenValidity === 'valid'" class="status-valid">{{ t('settings.valid') }}</span>
              <span v-else-if="githubTokenValidity === 'invalid'" class="status-invalid">{{ t('settings.invalid') }}</span>
              <span v-else>&mdash;</span>
              <button class="btn btn-sm btn-secondary" @click="onCheckGithubToken">{{ t('settings.checkValidity') }}</button>
            </div>
          </div>
          <div class="input-right">
            <input type="password" :value="githubTokenInput" @input="githubTokenInput = ($event.target as HTMLInputElement).value" @blur="onGithubTokenBlur" placeholder="ghp_..." class="pw-input">
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.librariesio.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.librariesio.enable') }}</div>
            <div class="setting-desc">
              {{ t('settings.librariesio.enableDesc') }}
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="librariesioEnabled" @change="debouncedAutoSave({ librariesio_enabled: librariesioEnabled })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.librariesio.apiKey') }}</div>
            <div class="setting-desc">
              {{ t('settings.librariesio.apiKeyDesc') }}
            </div>
            <div class="setting-desc link-desc">
              <a href="https://libraries.io/login" target="_blank">{{ t('settings.librariesio.loginHint') }}</a>
            </div>
            <div class="setting-desc status-desc">
              {{ t('settings.librariesio.status') }} <span :class="tokenSet.librariesio_api_key ? 'status-set' : 'status-not-set'">{{ tokenSet.librariesio_api_key ? t('settings.set') : t('settings.notSet') }}</span>
              <button v-if="tokenSet.librariesio_api_key" class="btn btn-danger btn-sm" @click="clearLibrariesIoKey">{{ t('settings.clearKey') }}</button>
            </div>
          </div>
          <div class="input-right">
            <input type="password" :value="librariesioKeyInput" @input="librariesioKeyInput = ($event.target as HTMLInputElement).value" @blur="onLibrariesIoKeyBlur" placeholder="libraries.io API key" class="pw-input">
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.ecosystems.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.ecosystems.enable') }}</div>
            <div class="setting-desc">
              {{ t('settings.ecosystems.enableDesc') }}
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="ecosystemsEnabled" @change="debouncedAutoSave({ ecosystems_enabled: ecosystemsEnabled })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.ecosystems.apiKey') }}</div>
            <div class="setting-desc">
              {{ t('settings.ecosystems.apiKeyDesc') }}
            </div>
            <div class="setting-desc status-desc">
              {{ t('settings.ecosystems.status') }} <span :class="tokenSet.ecosystems_api_key ? 'status-set' : 'status-not-set'">{{ tokenSet.ecosystems_api_key ? t('settings.set') : t('settings.notSet') }}</span>
              <button v-if="tokenSet.ecosystems_api_key" class="btn btn-danger btn-sm" @click="clearEcosystemsKey">{{ t('settings.clearKey') }}</button>
            </div>
          </div>
          <div class="input-right">
            <input type="password" :value="ecosystemsKeyInput" @input="ecosystemsKeyInput = ($event.target as HTMLInputElement).value" @blur="onEcosystemsKeyBlur" placeholder="ecosyste.ms API key (optional)" class="pw-input">
          </div>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.ecosystems.maxRps') }}</div>
            <div class="setting-desc">
              {{ t('settings.ecosystems.maxRpsDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="ecosystemsMaxRequestsPerSecond" min="0.1" max="100" step="0.1" @change="debouncedAutoSave({ ecosystems_max_requests_per_second: ecosystemsMaxRequestsPerSecond })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.resolverBehaviour.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.resolverBehaviour.maxRetries') }}</div>
            <div class="setting-desc">
              {{ t('settings.resolverBehaviour.maxRetriesDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="retryMaxAttempts" min="1" max="10" @change="debouncedAutoSave({ retry_max_attempts: retryMaxAttempts })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.resolverBehaviour.cooldown') }}</div>
            <div class="setting-desc">
              {{ t('settings.resolverBehaviour.cooldownDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="retryBaseCooldownSeconds" min="0.5" max="120" step="0.5" @change="debouncedAutoSave({ retry_base_cooldown_seconds: retryBaseCooldownSeconds })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.network.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.network.batchLimit') }}</div>
            <div class="setting-desc">
              {{ t('settings.network.batchLimitDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="batchSemaphoreLimit" min="1" max="100" @change="debouncedAutoSave({ batch_semaphore_limit: batchSemaphoreLimit })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.network.probeUrl') }}</div>
            <div class="setting-desc">
              {{ t('settings.network.probeUrlDesc') }}
            </div>
          </div>
          <input type="text" v-model="connectivityUrl" @blur="debouncedAutoSave({ connectivity_url: connectivityUrl })" class="txt-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.network.probeTimeout') }}</div>
            <div class="setting-desc">
              {{ t('settings.network.probeTimeoutDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="connectivityTimeout" min="1" max="30" @change="debouncedAutoSave({ connectivity_timeout: connectivityTimeout })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.jobManagement.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.jobManagement.ttlLabel') }}</div>
            <div class="setting-desc">
              {{ t('settings.jobManagement.ttlDesc') }}
            </div>
          </div>
          <input type="number" v-model.number="jobTtlHours" min="1" max="720" @change="debouncedAutoSave({ job_ttl_hours: jobTtlHours })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.logging.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.logging.logLevel') }}</div>
            <div class="setting-desc">
              {{ t('settings.logging.logLevelDesc') }}
            </div>
          </div>
          <select v-model="logLevel" @change="debouncedAutoSave({ log_level: logLevel })" class="select-input">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ t('settings.jsonFormat.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.jsonFormat.indentSize') }}</div>
            <div class="setting-desc">
              {{ t('settings.jsonFormat.indentSizeDesc') }}
            </div>
          </div>
          <select v-model.number="jsonIndent" @change="debouncedAutoSave({ json_indent: jsonIndent })" class="select-input">
            <option :value="1">{{ t('settings.jsonFormat.spaces', { count: 1 }) }}</option>
            <option :value="2">{{ t('settings.jsonFormat.spaces', { count: 2 }) }}</option>
            <option :value="4">{{ t('settings.jsonFormat.spaces', { count: 4 }) }}</option>
          </select>
        </div>
      </div>

      <div v-if="toast" :class="['toast', toast.isError ? 'toast-err' : 'toast-ok']">
        {{ toast.text }}
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '../stores/useSettingsStore'
import { clearValidationCache } from '../api/settings'
import type { SettingsUpdate } from '../types/api'
import { useI18n } from 'vue-i18n'

const store = useSettingsStore()
const { t, locale } = useI18n()
const {
  validateDbUrls, validateSbomRefs, sbomMultipleVcsBehavior, urlValidationTimeout, revalidationCooldownHours,
  retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
  librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
  batchSemaphoreLimit, jobTtlHours, connectivityUrl, connectivityTimeout,
  tokenSet, loading, jsonIndent, githubTokenValidity,
} = storeToRefs(store)

const githubTokenInput = ref('')
const librariesioKeyInput = ref('')
const ecosystemsKeyInput = ref('')

const toast = ref<{ text: string; isError: boolean } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(text: string, isError: boolean) {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { text, isError }
  toastTimer = setTimeout(() => { toast.value = null; toastTimer = null }, isError ? 5000 : 3000)
}

function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { timer = null; fn(...args) }, ms)
  }) as T
}

function autoSave(partial: SettingsUpdate) {
  store.save(partial)
    .then(() => store.load())
    .then(() => {
      showToast(t('settings.savedToast'), false)
      if ('github_token' in partial) githubTokenInput.value = ''
      if ('librariesio_api_key' in partial) librariesioKeyInput.value = ''
      if ('ecosystems_api_key' in partial) ecosystemsKeyInput.value = ''
    })
    .catch((err: Error) => {
      const apiErr = err as import('../api/client').ApiError
      const msg = apiErr.error ? t('errors.' + apiErr.error, apiErr.data) : err.message
      showToast(t('settings.saveFailedToast', { message: msg }), true)
    })
}

const debouncedAutoSave = debounce(autoSave, 500)

async function onGithubTokenBlur() {
  const value = githubTokenInput.value.trim()
  if (!value) return
  await autoSave({ github_token: value } as SettingsUpdate)
}

async function onLibrariesIoKeyBlur() {
  const value = librariesioKeyInput.value.trim()
  if (!value) return
  await autoSave({ librariesio_api_key: value } as SettingsUpdate)
}

async function onEcosystemsKeyBlur() {
  const value = ecosystemsKeyInput.value.trim()
  if (!value) return
  await autoSave({ ecosystems_api_key: value } as SettingsUpdate)
}

async function clearToken() {
  try {
    await store.clearToken('github_token')
    showToast(t('settings.tokenCleared'), false)
    await store.load()
  } catch { showToast(t('settings.errorMessages.tokenClearFailed'), true) }
}

async function onCheckGithubToken() {
  try {
    await store.checkGithubToken()
    showToast(t('settings.tokenCheckComplete'), false)
  } catch {
    showToast(t('settings.errorMessages.tokenCheckFailed'), true)
  }
}

async function clearLibrariesIoKey() {
  try {
    await store.clearToken('librariesio_api_key')
    showToast(t('settings.tokenCleared'), false)
    await store.load()
  } catch { showToast(t('settings.errorMessages.keyClearFailed'), true) }
}

async function clearEcosystemsKey() {
  try {
    await store.clearToken('ecosystems_api_key')
    showToast(t('settings.tokenCleared'), false)
    await store.load()
  } catch { showToast(t('settings.errorMessages.keyClearFailed'), true) }
}

async function onClearValidationCache() {
  try {
    await clearValidationCache()
    showToast(t('settings.cacheCleared'), false)
  } catch {
    showToast(t('settings.errorMessages.cacheClearFailed'), true)
  }
}

async function setLanguage(e: Event) {
  const lang = (e.target as HTMLSelectElement).value
  try {
    await store.save({ language: lang } as SettingsUpdate)
    locale.value = lang
    localStorage.setItem('locale', lang)
    showToast(t('settings.savedToast'), false)
  } catch (err) {
    const apiErr = err as import('../api/client').ApiError
    const msg = apiErr.error ? t('errors.' + apiErr.error, apiErr.data) : t('settings.errorMessages.loadFailed')
    showToast(msg, true)
  }
}

onMounted(async () => {
  try {
    await store.load()
    // Sync language from backend
    if (store.language && store.language !== locale.value) {
      locale.value = store.language
      localStorage.setItem('locale', store.language)
    }
  } catch {
    showToast(t('settings.errorMessages.loadFailed'), true)
  }
  loading.value = false
})

onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<style scoped>
.settings-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 2rem 1rem;
  flex: 1;
}

h1 {
  font-size: 1.5rem;
  margin-bottom: 0.25rem;
}

.subtitle {
  color: var(--color-muted);
  margin-bottom: 1.5rem;
}

.card {
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 1.5rem;
  box-shadow: var(--color-card-shadow);
  margin-top: 1rem;
}

.card:first-of-type {
  margin-top: 0;
}

.card-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--color-muted-light);
  margin-bottom: 1rem;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--color-setting-border);
}

.setting-row:last-of-type {
  border-bottom: none;
}

.setting-disabled {
  opacity: 0.5;
  pointer-events: none;
}

.setting-label {
  font-weight: 500;
}

.setting-desc {
  font-size: 0.85rem;
  color: var(--color-muted);
  margin-top: 0.25rem;
}

.link-desc {
  margin-top: 0.25rem;
}

.status-desc {
  margin-top: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.status-set {
  font-weight: 600;
  color: var(--color-success);
}

.status-not-set {
  font-weight: 600;
  color: var(--color-error);
}

.status-valid {
  font-weight: 600;
  color: var(--color-success);
}

.status-invalid {
  font-weight: 600;
  color: var(--color-error);
}

.validity-desc {
  margin-top: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.num-input {
  width: 80px;
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  text-align: center;
}

.num-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.txt-input {
  width: 240px;
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
}
.txt-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.pw-input {
  width: 240px;
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
}

.pw-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.input-right {
  text-align: right;
  flex-shrink: 0;
}

.select-input {
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
}

.select-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.btn-small {
  margin-left: 0.5rem;
}

.toast {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 1000;
  padding: 0.75rem 1rem;
  border-radius: var(--border-radius);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  max-width: 360px;
  animation: toast-in 0.2s ease-out;
}

.toast-ok {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.toast-err {
  background: var(--color-error-bg);
  color: var(--color-error);
}

@keyframes toast-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>