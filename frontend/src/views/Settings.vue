<template>
  <div class="settings-page">
    <h1>sbom-helper</h1>
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
            <input type="checkbox" v-model="validateDbUrls">
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
          <input type="number" v-model.number="urlValidationTimeout" min="1" max="60" class="num-input">
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
          <input type="number" v-model.number="revalidationCooldownHours" min="0" max="720" class="num-input">
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
            <input type="password" v-model="githubTokenInput" placeholder="ghp_..." class="pw-input">
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
            <input type="checkbox" v-model="librariesioEnabled">
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
            <input type="password" v-model="librariesioKeyInput" placeholder="libraries.io API key" class="pw-input">
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
            <input type="checkbox" v-model="ecosystemsEnabled">
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
            <input type="password" v-model="ecosystemsKeyInput" placeholder="ecosyste.ms API key (optional)" class="pw-input">
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
          <input type="number" v-model.number="ecosystemsMaxRequestsPerSecond" min="0.1" max="100" step="0.1" class="num-input">
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
          <input type="number" v-model.number="retryMaxAttempts" min="1" max="10" class="num-input">
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
          <input type="number" v-model.number="retryBaseCooldownSeconds" min="0.5" max="120" step="0.5" class="num-input">
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
          <select v-model="logLevel" class="select-input">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
        </div>
      </div>

      <button class="save-btn" :disabled="saving" @click="saveSettings">Save</button>

      <div v-if="message" :class="['msg', message.isError ? 'msg-err' : 'msg-ok']">
        {{ message.text }}
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSettings, updateSettings } from '../api/settings'
import type { SettingsTokenSet } from '../types/api'

const validateDbUrls = ref(false)
const urlValidationTimeout = ref(5)
const revalidationCooldownHours = ref(24)
const retryMaxAttempts = ref(3)
const retryBaseCooldownSeconds = ref(5)
const logLevel = ref('INFO')
const librariesioEnabled = ref(false)
const ecosystemsEnabled = ref(false)
const ecosystemsMaxRequestsPerSecond = ref(2)
const tokenSet = ref<SettingsTokenSet>({ github_token: false, librariesio_api_key: false, ecosystems_api_key: false })
const githubTokenInput = ref('')
const librariesioKeyInput = ref('')
const ecosystemsKeyInput = ref('')
const loading = ref(true)
const saving = ref(false)
const message = ref<{ text: string; isError: boolean } | null>(null)

let messageTimer: ReturnType<typeof setTimeout> | null = null

function showMessage(text: string, isError: boolean) {
  if (messageTimer) clearTimeout(messageTimer)
  message.value = { text, isError }
  messageTimer = setTimeout(() => {
    message.value = null
  }, 3000)
}

async function loadSettings() {
  try {
    const data = await getSettings()
    validateDbUrls.value = data.validate_db_urls
    urlValidationTimeout.value = data.url_validation_timeout
    revalidationCooldownHours.value = data.revalidation_cooldown_hours
    retryMaxAttempts.value = data.retry_max_attempts
    retryBaseCooldownSeconds.value = data.retry_base_cooldown_seconds
    logLevel.value = data.log_level
    librariesioEnabled.value = data.librariesio_enabled
    ecosystemsEnabled.value = data.ecosystems_enabled
    ecosystemsMaxRequestsPerSecond.value = data.ecosystems_max_requests_per_second
    tokenSet.value = data.token_set
  } catch {
    showMessage('Failed to load settings', true)
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const body: Record<string, unknown> = {
      validate_db_urls: validateDbUrls.value,
      url_validation_timeout: urlValidationTimeout.value,
      revalidation_cooldown_hours: revalidationCooldownHours.value,
      librariesio_enabled: librariesioEnabled.value,
      ecosystems_enabled: ecosystemsEnabled.value,
      ecosystems_max_requests_per_second: ecosystemsMaxRequestsPerSecond.value,
      retry_max_attempts: retryMaxAttempts.value,
      retry_base_cooldown_seconds: retryBaseCooldownSeconds.value,
      log_level: logLevel.value,
    }
    if (githubTokenInput.value.trim() !== '') {
      body.github_token = githubTokenInput.value.trim()
    }
    if (librariesioKeyInput.value.trim() !== '') {
      body.librariesio_api_key = librariesioKeyInput.value.trim()
    }
    if (ecosystemsKeyInput.value.trim() !== '') {
      body.ecosystems_api_key = ecosystemsKeyInput.value.trim()
    }
    await updateSettings(body)
    showMessage('Settings saved', false)
    githubTokenInput.value = ''
    librariesioKeyInput.value = ''
    ecosystemsKeyInput.value = ''
    await loadSettings()
  } catch {
    showMessage('Failed to save settings', true)
  } finally {
    saving.value = false
  }
}

async function clearToken() {
  try {
    await updateSettings({ github_token: null })
    showMessage('Token cleared', false)
    await loadSettings()
  } catch {
    showMessage('Failed to clear token', true)
  }
}

async function clearLibrariesIoKey() {
  try {
    await updateSettings({ librariesio_api_key: null })
    showMessage('Libraries.io key cleared', false)
    await loadSettings()
  } catch {
    showMessage('Failed to clear key', true)
  }
}

async function clearEcosystemsKey() {
  try {
    await updateSettings({ ecosystems_api_key: null })
    showMessage('ecosyste.ms key cleared', false)
    await loadSettings()
  } catch {
    showMessage('Failed to clear key', true)
  }
}

onMounted(async () => {
  await loadSettings()
  loading.value = false
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

.save-btn {
  margin-top: 1rem;
  padding: 0.75rem 1.5rem;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 1rem;
  cursor: pointer;
}

.save-btn:hover {
  background: var(--color-primary-hover);
}

.save-btn:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
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

.msg {
  margin-top: 0.75rem;
  padding: 0.75rem;
  border-radius: var(--border-radius);
}

.msg-ok {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.msg-err {
  background: var(--color-error-bg);
  color: var(--color-error);
}
</style>