<template>
  <div class="container">
    <h1>{{ t('purlResolver.title') }}</h1>
    <p class="subtitle">{{ t('purlResolver.subtitle') }}</p>

    <form class="form-group" @submit.prevent="handleResolve">
      <textarea
        v-model="purlInput"
        :placeholder="t('purlResolver.placeholder')"
        rows="5"
      ></textarea>
      <button type="submit" class="btn btn-primary" :disabled="loading">{{ t('purlResolver.resolve') }}</button>
    </form>

    <div v-if="loading" class="loading">
      <span class="spinner"></span> {{ t('purlResolver.resolving') }}
    </div>

    <div v-if="results.length" class="result">
      <table class="result-table">
        <thead>
          <tr>
            <th>{{ t('purlResolver.purl') }}</th>
            <th>{{ t('purlResolver.repoUrl') }}</th>
            <th>{{ t('purlResolver.foundBy') }}</th>
            <th>{{ t('purlResolver.resolver') }}</th>
            <th>{{ t('purlResolver.warnings') }}</th>
            <th>{{ t('purlResolver.status') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in results" :key="item.purl">
            <td class="purl-cell">{{ item.purl }}</td>
            <td>
              <a v-if="item.repository_url" :href="item.repository_url" target="_blank">{{ item.repository_url }}</a>
              <span v-else class="muted">&mdash;</span>
            </td>
            <td>{{ item.found_by || '—' }}</td>
            <td>{{ item.resolver || '—' }}</td>
            <td>
              <ul v-if="item.warnings && item.warnings.length" class="warnings-list">
                <li v-for="(warning, i) in item.warnings" :key="i">{{ warning }}</li>
              </ul>
              <span v-else class="muted">&mdash;</span>
            </td>
            <td>
              <span :class="statusClass(item)" class="status-badge">{{ statusText(item) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolvePurls } from '../api/purl'
import { ApiError } from '../api/client'
import type { BatchResolveItem } from '../types/api'

const { t, te } = useI18n()

const purlInput = ref('')
const loading = ref(false)
const results = ref<BatchResolveItem[]>([])
const error = ref<string | null>(null)

function statusText(item: BatchResolveItem): string {
  if (item.error) {
    const key = 'errors.' + item.error
    return te(key) ? t(key) : item.error
  }
  if (item.repository_url) return t('purlResolver.statusResolved')
  return t('purlResolver.statusNotFound')
}

function statusClass(item: BatchResolveItem): string {
  if (item.error) return 'status-error'
  if (item.repository_url) return 'status-resolved'
  return 'status-notfound'
}

async function handleResolve() {
  const purls = purlInput.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  if (!purls.length) return

  results.value = []
  error.value = null
  loading.value = true

  try {
    const res = await resolvePurls({ purls })
    results.value = res.results
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
  max-width: 960px;
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
  flex-direction: column;
  gap: 0.5rem;
}

textarea {
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 1rem;
  font-family: inherit;
  resize: vertical;
  box-sizing: border-box;
}

textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus);
}

.form-group .btn {
  align-self: flex-start;
}

.result {
  margin-top: 1.5rem;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.result-table th,
.result-table td {
  border: 1px solid var(--color-input-border);
  padding: 0.5rem 0.75rem;
  text-align: left;
  vertical-align: top;
  word-break: break-all;
}

.result-table th {
  background: var(--color-card-header-bg, transparent);
  font-weight: 600;
}

.result-table a {
  color: var(--color-primary);
  text-decoration: none;
}

.result-table a:hover {
  text-decoration: underline;
}

.purl-cell {
  font-family: monospace;
}

.warnings-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.warnings-list li {
  padding: 0.15rem 0;
}

.status-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: var(--border-radius);
  font-size: 0.75rem;
  white-space: nowrap;
}

.status-resolved {
  background: var(--color-success-bg, #e6f4ea);
  color: var(--color-success, #1a7f37);
}

.status-notfound {
  background: var(--color-warning-bg, #fff8e6);
  color: var(--color-warning, #9a6700);
}

.status-error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.muted {
  color: var(--color-muted);
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
