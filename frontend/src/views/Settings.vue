<template>
  <div class="settings-page">
    <h1>Settings</h1>
    <p class="subtitle">Application settings</p>

    <div v-if="loading" class="loading">
      <span class="spinner"></span>
      Loading settings…
    </div>

    <template v-if="!loading">
      <div class="card">
        <div class="card-title">URL Validation</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Validate URLs from local database</div>
            <div class="setting-desc">
              When enabled, repository URLs found in the local database are verified
              (HTTP HEAD + git ls-remote) before being returned. Invalid URLs are
              deleted and resolution continues through the resolver chain.
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="validateDbUrls" @change="debouncedAutoSave({ validate_db_urls: validateDbUrls })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Validate pre-existing URLs from SBOM</div>
            <div class="setting-desc">
              When enabled, existing VCS and source-distribution URLs found in SBOM
              files are verified before enrichment. Invalid URLs trigger re-resolution
              of the component.
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="validateSbomRefs" @change="debouncedAutoSave({ validate_sbom_refs: validateSbomRefs })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Validation timeout (seconds)</div>
            <div class="setting-desc">
              Timeout for each HTTP HEAD and git ls-remote check (1-60 seconds).
            </div>
          </div>
          <input type="number" v-model.number="urlValidationTimeout" min="1" max="60" @change="debouncedAutoSave({ url_validation_timeout: urlValidationTimeout })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Re-validation cooldown (hours)</div>
            <div class="setting-desc">
              When set to 24 (default), URLs cached by trusted resolvers
              (purl2repo, ecosyste.ms, libraries.io) are re-validated at most once per day.
              Entries from imports or manual edits are always re-validated regardless of cooldown.
              Set to 0 to disable cooldown and always validate.
            </div>
          </div>
          <input type="number" v-model.number="revalidationCooldownHours" min="0" max="720" @change="debouncedAutoSave({ revalidation_cooldown_hours: revalidationCooldownHours })" class="num-input">
        </div>
        <div class="setting-row info-row">
          <div class="setting-desc">
            URLs returned by resolvers are always validated before being returned.
            Validation results are cached and reused across all contexts
            (local database, SBOM enrichment) within the configured cooldown period.
          </div>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Clear validation cache</div>
            <div class="setting-desc">
              Remove all cached URL validation results. The next validation for each
              URL will perform a full check.
            </div>
          </div>
          <button class="btn-secondary" @click="onClearValidationCache">Clear cache</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">GitHub API Token (optional)</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">GitHub Personal Access Token</div>
            <div class="setting-desc">
              Used for authenticated git ls-remote and HTTP requests.
              Increases rate limits from 60/hr to 5000/hr for API,
              and removes limits for git operations.
            </div>
            <div class="setting-desc link-desc">
              <a href="https://github.com/settings/tokens" target="_blank">Generate token</a>
              → Settings → Developer settings → Personal access tokens → Fine-grained or classic
            </div>
            <div class="setting-desc status-desc">
              Status: <span :class="tokenSet.github_token ? 'status-set' : 'status-not-set'">{{ tokenSet.github_token ? 'set' : 'not set' }}</span>
              <button v-if="tokenSet.github_token" class="btn-danger btn-small" @click="clearToken">Clear token</button>
            </div>
          </div>
          <div class="input-right">
            <input type="password" :value="githubTokenInput" @input="githubTokenInput = ($event.target as HTMLInputElement).value" @blur="onGithubTokenBlur" placeholder="ghp_..." class="pw-input">
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Libraries.io Resolver (optional)</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Enable libraries.io resolver</div>
            <div class="setting-desc">
              When enabled, libraries.io is used as a fallback resolver
              when purl2repo cannot find a repository URL.
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="librariesioEnabled" @change="debouncedAutoSave({ librariesio_enabled: librariesioEnabled })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">API Key</div>
            <div class="setting-desc">
              Optional API key for higher rate limits (60 req/min vs 10 req/min).
            </div>
            <div class="setting-desc link-desc">
              <a href="https://libraries.io/login" target="_blank">Log in to libraries.io</a>
              → API Settings
            </div>
            <div class="setting-desc status-desc">
              Status: <span :class="tokenSet.librariesio_api_key ? 'status-set' : 'status-not-set'">{{ tokenSet.librariesio_api_key ? 'set' : 'not set' }}</span>
              <button v-if="tokenSet.librariesio_api_key" class="btn-danger btn-small" @click="clearLibrariesIoKey">Clear key</button>
            </div>
          </div>
          <div class="input-right">
            <input type="password" :value="librariesioKeyInput" @input="librariesioKeyInput = ($event.target as HTMLInputElement).value" @blur="onLibrariesIoKeyBlur" placeholder="libraries.io API key" class="pw-input">
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">ecosyste.ms Resolver (optional)</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Enable ecosyste.ms resolver</div>
            <div class="setting-desc">
              Live query to ecosyste.ms API for repository URL lookup.
              Works without API key. Key is optional for higher rate limits.
            </div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="ecosystemsEnabled" @change="debouncedAutoSave({ ecosystems_enabled: ecosystemsEnabled })">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">API Key (optional)</div>
            <div class="setting-desc">
              Optional API key for higher rate limits.
            </div>
            <div class="setting-desc status-desc">
              Status: <span :class="tokenSet.ecosystems_api_key ? 'status-set' : 'status-not-set'">{{ tokenSet.ecosystems_api_key ? 'set' : 'not set' }}</span>
              <button v-if="tokenSet.ecosystems_api_key" class="btn-danger btn-small" @click="clearEcosystemsKey">Clear key</button>
            </div>
          </div>
          <div class="input-right">
            <input type="password" :value="ecosystemsKeyInput" @input="ecosystemsKeyInput = ($event.target as HTMLInputElement).value" @blur="onEcosystemsKeyBlur" placeholder="ecosyste.ms API key (optional)" class="pw-input">
          </div>
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Max requests per second</div>
            <div class="setting-desc">
              Rate limit for ecosyste.ms API requests (0.1–100 req/s).
              Default: 2.0. Lower values reduce timeout risk under concurrent load.
            </div>
          </div>
          <input type="number" v-model.number="ecosystemsMaxRequestsPerSecond" min="0.1" max="100" step="0.1" @change="debouncedAutoSave({ ecosystems_max_requests_per_second: ecosystemsMaxRequestsPerSecond })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">Resolver Behaviour</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Max retry attempts</div>
            <div class="setting-desc">
              Maximum HTTP request attempts per resolver (including the first).
              Applied to ecosyste.ms and libraries.io on timeout, rate limit (429), and server errors (5xx).
              Default: 3. Range: 1–10.
            </div>
          </div>
          <input type="number" v-model.number="retryMaxAttempts" min="1" max="10" @change="debouncedAutoSave({ retry_max_attempts: retryMaxAttempts })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Retry cooldown (seconds)</div>
            <div class="setting-desc">
              Base wait time between retries. Actual wait = cooldown × (attempt − 1).
              Example: cooldown=5 → waits 5s before 2nd attempt, 10s before 3rd.
              Range: 0.5–120 seconds.
            </div>
          </div>
          <input type="number" v-model.number="retryBaseCooldownSeconds" min="0.5" max="120" step="0.5" @change="debouncedAutoSave({ retry_base_cooldown_seconds: retryBaseCooldownSeconds })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">Network & Performance</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Batch concurrency limit</div>
            <div class="setting-desc">
              Maximum number of parallel PURL resolution requests in a batch (1–100). Default: 10.
            </div>
          </div>
          <input type="number" v-model.number="batchSemaphoreLimit" min="1" max="100" @change="debouncedAutoSave({ batch_semaphore_limit: batchSemaphoreLimit })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Connectivity probe URL</div>
            <div class="setting-desc">
              Target URL used to check internet access before URL validation. Set to empty to disable the probe.
            </div>
          </div>
          <input type="text" v-model="connectivityUrl" @blur="debouncedAutoSave({ connectivity_url: connectivityUrl })" class="txt-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Connectivity probe timeout (seconds)</div>
            <div class="setting-desc">
              Timeout for the connectivity HEAD request (1–30 seconds). Default: 2.
            </div>
          </div>
          <input type="number" v-model.number="connectivityTimeout" min="1" max="30" @change="debouncedAutoSave({ connectivity_timeout: connectivityTimeout })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Rate-limit cooldown (seconds)</div>
            <div class="setting-desc">
              How long to pause URL validation after consecutive rate-limited responses (1–600 seconds). Default: 60.
            </div>
          </div>
          <input type="number" v-model.number="rateLimitCooldown" min="1" max="600" @change="debouncedAutoSave({ rate_limit_cooldown: rateLimitCooldown })" class="num-input">
        </div>
      </div>

      <div class="card">
        <div class="card-title">Logging</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Log level</div>
            <div class="setting-desc">
              Controls which log messages are shown in docker compose logs.
              DEBUG – all messages, INFO – general operations, WARNING – errors only.
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
        <div class="card-title">JSON Format</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">JSON indent size</div>
            <div class="setting-desc">
              Number of spaces used when indenting JSON in downloaded files (SBOM, Images List).
            </div>
          </div>
          <select v-model.number="jsonIndent" @change="debouncedAutoSave({ json_indent: jsonIndent })" class="select-input">
            <option :value="1">1 space</option>
            <option :value="2">2 spaces</option>
            <option :value="4">4 spaces</option>
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

const store = useSettingsStore()
const {
  validateDbUrls, validateSbomRefs, urlValidationTimeout, revalidationCooldownHours,
  retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
  librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
  batchSemaphoreLimit, connectivityUrl, connectivityTimeout, rateLimitCooldown,
  tokenSet, loading, jsonIndent,
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
      showToast('Settings saved', false)
      if ('github_token' in partial) githubTokenInput.value = ''
      if ('librariesio_api_key' in partial) librariesioKeyInput.value = ''
      if ('ecosystems_api_key' in partial) ecosystemsKeyInput.value = ''
    })
    .catch((err: Error) => showToast(`Failed to save: ${err.message}`, true))
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
    showToast('Token cleared', false)
    await store.load()
  } catch { showToast('Failed to clear token', true) }
}

async function clearLibrariesIoKey() {
  try {
    await store.clearToken('librariesio_api_key')
    showToast('Libraries.io key cleared', false)
    await store.load()
  } catch { showToast('Failed to clear key', true) }
}

async function clearEcosystemsKey() {
  try {
    await store.clearToken('ecosystems_api_key')
    showToast('ecosyste.ms key cleared', false)
    await store.load()
  } catch { showToast('Failed to clear key', true) }
}

async function onClearValidationCache() {
  try {
    await clearValidationCache()
    showToast('Validation cache cleared', false)
  } catch {
    showToast('Failed to clear validation cache', true)
  }
}

onMounted(async () => {
  try {
    await store.load()
  } catch {
    showToast('Failed to load settings', true)
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
}

.status-set {
  font-weight: 600;
  color: var(--color-success);
}

.status-not-set {
  font-weight: 600;
  color: var(--color-error);
}

.toggle {
  position: relative;
  width: 48px;
  height: 26px;
  cursor: pointer;
  flex-shrink: 0;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-toggle-off);
  border-radius: 26px;
  transition: background 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  height: 20px;
  width: 20px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle input:checked + .toggle-slider {
  background: var(--color-toggle-on);
}

.toggle input:checked + .toggle-slider::before {
  transform: translateX(22px);
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

.btn-danger {
  background: var(--color-danger);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  cursor: pointer;
}

.btn-danger:hover {
  background: var(--color-danger-hover);
}

.btn-small {
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
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