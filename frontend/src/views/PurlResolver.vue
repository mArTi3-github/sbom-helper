<template>
  <div class="container">
    <h1>{{ t('purlResolver.title') }}</h1>
    <p class="subtitle">{{ t('purlResolver.subtitle') }}</p>

    <form class="form-group" @submit.prevent="handleResolve">
      <input
        v-model="purlInput"
        type="text"
        :placeholder="t('purlResolver.placeholder')"
        required
      />
      <button type="submit" :disabled="loading">{{ t('purlResolver.resolve') }}</button>
    </form>

    <div v-if="loading" class="loading">
      <span class="spinner"></span> {{ t('purlResolver.resolving') }}
    </div>

    <div v-if="result" class="result">
      <div class="card">
        <div class="card-title">{{ t('purlResolver.repoUrl') }}</div>
        <div class="repo-url">
          <a v-if="result.repository_url" :href="result.repository_url" target="_blank">{{ result.repository_url }}</a>
          <span v-else>{{ t('purlResolver.noRepoUrl') }}</span>
        </div>
        <div class="meta">
          <span :class="['badge', confidenceClass]">{{ result.confidence || 'unknown' }}</span>
        </div>
        <button
          v-if="hasDetails"
          class="details-toggle"
          @click="showDetails = !showDetails"
        >
          {{ showDetails ? t('purlResolver.hideDetails') : t('purlResolver.showDetails') }}
        </button>
        <div v-if="showDetails && hasDetails" class="details show">
          <dl>
            <template v-if="result.repository_type">
              <dt>{{ t('purlResolver.repoType') }}</dt>
              <dd>{{ result.repository_type }}</dd>
            </template>
            <template v-if="result.repository_kind">
              <dt>{{ t('purlResolver.repoKind') }}</dt>
              <dd>{{ result.repository_kind }}</dd>
            </template>
            <template v-if="result.evidence && result.evidence.length">
              <dt>{{ t('purlResolver.evidence') }}</dt>
              <dd>
                <ul>
                  <li v-for="(item, i) in result.evidence" :key="i">{{ item }}</li>
                </ul>
              </dd>
            </template>
            <template v-if="result.warnings && result.warnings.length">
              <dt class="warning">{{ t('purlResolver.warnings') }}</dt>
              <dd>
                <ul>
                  <li v-for="(item, i) in result.warnings" :key="i" class="warning">{{ item }}</li>
                </ul>
              </dd>
            </template>
            <template v-if="result.version_reference">
              <dt>{{ t('purlResolver.versionRef') }}</dt>
              <dd>
                <a :href="result.version_reference" target="_blank">{{ result.version_reference }}</a>
              </dd>
            </template>
            <template v-if="result.found_by">
              <dt>{{ t('purlResolver.foundBy') }}</dt>
              <dd>{{ result.found_by }}</dd>
            </template>
            <template v-if="result.resolver">
              <dt>{{ t('purlResolver.resolver') }}</dt>
              <dd>{{ result.resolver }}</dd>
            </template>
          </dl>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolvePurl } from '../api/purl'
import { ApiError } from '../api/client'
import type { ResolveResponse } from '../types/api'

const { t } = useI18n()

const purlInput = ref('')
const loading = ref(false)
const result = ref<ResolveResponse | null>(null)
const error = ref<string | null>(null)
const showDetails = ref(false)

const confidenceClass = computed(() => {
  if (!result.value?.confidence) return 'badge-low'
  return 'badge-' + result.value.confidence
})

const hasDetails = computed(() => {
  const r = result.value
  if (!r) return false
  return !!(r.repository_type || r.repository_kind || (r.evidence && r.evidence.length) || (r.warnings && r.warnings.length) || r.version_reference || r.found_by || r.resolver)
})

async function handleResolve() {
  const purl = purlInput.value.trim()
  if (!purl) return

  result.value = null
  error.value = null
  showDetails.value = false
  loading.value = true

  try {
    const res = await resolvePurl({ purl })
    result.value = res
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      error.value = t('errors.' + e.error, e.data)
    } else if (e instanceof Error) {
      error.value = t('errors.network_error')
    } else {
      error.value = t('errors.unexpected_error')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.container {
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

.form-group {
  display: flex;
  gap: 0.5rem;
}

input[type="text"] {
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 1rem;
}

input[type="text"]:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus);
}

button {
  padding: 0.75rem 1.5rem;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 1rem;
  cursor: pointer;
  white-space: nowrap;
}

button:hover {
  background: var(--color-primary-hover);
}

button:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
}

.result {
  margin-top: 1.5rem;
}

.repo-url {
  font-size: 1.1rem;
  word-break: break-all;
}

.repo-url a {
  color: var(--color-primary);
  text-decoration: none;
}

.repo-url a:hover {
  text-decoration: underline;
}

.meta {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.75rem;
}

.details-toggle {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: 0.875rem;
  padding: 0;
  margin-top: 0.75rem;
}

.details-toggle:hover {
  text-decoration: underline;
}

.details {
  margin-top: 0.75rem;
  font-size: 0.875rem;
  color: #555;
}

.details dt {
  font-weight: 600;
  margin-top: 0.5rem;
}

.details dd {
  margin-left: 0;
}

.details ul {
  list-style: none;
  padding: 0;
}

.details li {
  padding: 0.25rem 0;
}

.warning {
  color: var(--color-error);
}

.error-msg {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--border-radius);
  padding: 1rem;
  color: var(--color-error);
  margin-top: 1.5rem;
}

.loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1rem;
  color: var(--color-muted);
}
</style>
