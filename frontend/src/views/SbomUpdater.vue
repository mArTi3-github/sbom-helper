<template>
  <div class="container">
    <h1>{{ t('sbomUpdater.title') }}</h1>
    <p class="subtitle">{{ t('sbomUpdater.subtitle') }}</p>

    <FileUploadZone accept=".json" :max-size="200" @file-selected="onFileSelected" />

    <div class="options-section">
      <label class="checkbox-row">
        <input type="checkbox" v-model="removeUnresolved" />
        <span>{{ t('sbomUpdater.removeUnresolved') }}</span>
      </label>
    </div>

    <div class="card">
      <div class="card-title">{{ t('sbomUpdater.ignorePatterns') }}</div>
      <div class="pattern-rows">
        <div v-for="(row, idx) in patternRows" :key="idx" class="pattern-row">
          <input type="text" v-model="row.field" :placeholder="t('sbomUpdater.fieldPlaceholder')" class="pattern-input" />
          <span class="pattern-label">{{ t('sbomUpdater.contains') }}</span>
          <input type="text" v-model="row.pattern" :placeholder="t('sbomUpdater.valuePlaceholder')" class="pattern-input" />
          <button class="btn-delete" @click="removeRow(idx)">✕</button>
        </div>
      </div>
      <div class="pattern-toolbar">
        <button class="btn-secondary" @click="addRow">{{ t('sbomUpdater.addRow') }}</button>
        <button class="btn-primary" @click="savePatterns" :disabled="savingPatterns">{{ patternsSaved ? t('sbomUpdater.saved') : t('sbomUpdater.save') }}</button>
      </div>
    </div>

    <div class="toolbar">
      <button :disabled="!selectedFile || submitting" @click="handleProcess">{{ t('sbomUpdater.process') }}</button>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- Recent Jobs + Details -->
    <div v-if="jobs.length > 0" class="jobs-section">
      <RecentJobs :jobs="jobs" :active-id="activeJobId" @select="selectJob" />
    </div>

    <div v-if="activeJobId && activeJob" class="job-details">
      <!-- queued / running -->
      <div v-if="activeJob.status === 'queued' || activeJob.status === 'running'" class="loading">
        <span class="spinner"></span>
        <span>{{ t('sbomUpdater.processing') }}</span>
        <span v-if="activeJob.progress_total > 0" class="progress-text">
          ({{ activeJob.progress_current }} / {{ activeJob.progress_total }})
        </span>
        <button class="btn-cancel" @click="handleCancel" :disabled="cancelling">
          {{ t('common.cancel') }}
        </button>
      </div>

      <!-- completed -->
      <div v-if="activeJob.status === 'completed' && activeJob.summary" class="results">
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-value">{{ activeJob.summary.total_purls }}</div>
            <div class="summary-label">
              {{ t('sbomUpdater.total') }}
              <span class="info-icon" :data-tooltip="t('sbomUpdater.ttUniquePurls')">i</span>
            </div>
          </div>
          <div class="summary-item summary-found">
            <div class="summary-value">{{ activeJob.summary.found }}</div>
            <div class="summary-label">
              {{ t('sbomUpdater.found') }}
              <span class="info-icon" :data-tooltip="t('sbomUpdater.ttFoundRepo')">i</span>
            </div>
          </div>
          <div class="summary-item summary-not-found">
            <div class="summary-value">{{ activeJob.summary.not_found }}</div>
            <div class="summary-label">
              {{ t('sbomUpdater.notFound') }}
              <span class="info-icon" :data-tooltip="t('sbomUpdater.ttNotFound')">i</span>
            </div>
          </div>
          <div v-if="activeJob.summary.skipped > 0" class="summary-item summary-skipped">
            <div class="summary-value">{{ activeJob.summary.skipped }}</div>
            <div class="summary-label">
              {{ t('sbomUpdater.skipped') }}
              <span class="info-icon" :data-tooltip="t('sbomUpdater.ttSkipped')">i</span>
            </div>
          </div>
          <div v-if="activeJob.summary.removed > 0" class="summary-item summary-removed">
            <div class="summary-value">{{ activeJob.summary.removed }}</div>
            <div class="summary-label">
              {{ t('sbomUpdater.removed') }}
              <span class="info-icon" :data-tooltip="t('sbomUpdater.ttRemoved')">i</span>
            </div>
          </div>
          <div v-if="activeJob.summary.ignored > 0" class="summary-item summary-ignored">
            <div class="summary-value">{{ activeJob.summary.ignored }}</div>
            <div class="summary-label">
              {{ t('sbomUpdater.ignored') }}
              <span class="info-icon" :data-tooltip="t('sbomUpdater.ttIgnored')">i</span>
            </div>
          </div>
        </div>

        <div class="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{{ t('sbomUpdater.purl') }}</th>
                <th>{{ t('sbomUpdater.status') }}</th>
                <th>{{ t('sbomUpdater.repoUrl') }}</th>
                <th>{{ t('sbomUpdater.foundBy') }}</th>
                <th>{{ t('sbomUpdater.resolver') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, i) in activeJob.results" :key="i">
                <td class="cell-purl">{{ item.purl }}</td>
                <td>
                  <span :class="['status-badge', 'status-' + item.status]">{{ t('status.' + item.status) }}</span>
                </td>
                <td>
                  <a v-if="item.repository_url" :href="safeUrl(item.repository_url)" target="_blank">{{ item.repository_url }}</a>
                  <span v-else>—</span>
                </td>
                <td>{{ item.found_by || '—' }}</td>
                <td>{{ item.resolver || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="toolbar">
          <a :href="downloadResultUrl()" class="btn-primary" download>
            {{ t('sbomUpdater.downloadEnriched') }}
          </a>
        </div>
      </div>

      <!-- failed -->
      <div v-if="activeJob.status === 'failed'" class="error-msg">
        {{ activeJob.error_message || t('sbomUpdater.failed') }}
      </div>

      <!-- cancelled -->
      <div v-if="activeJob.status === 'cancelled'" class="info-msg">
        {{ t('sbomUpdater.cancelled') }}
      </div>

      <!-- Delete button for terminal statuses -->
      <div v-if="isTerminal(activeJob.status)" class="toolbar">
        <button class="btn-delete-job" @click="handleDelete" :disabled="deleting">
          {{ t('common.delete') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import FileUploadZone from '../components/FileUploadZone.vue'
import RecentJobs from '../components/RecentJobs.vue'
import { getIgnorePatterns, saveIgnorePatterns } from '../api/sbom'
import { createSbomEnrichJob, getJob, cancelJob, deleteJob, listJobs, downloadJobResultUrl } from '../api/jobs'
import { ApiError } from '../api/client'
import { safeUrl } from '../composables/useDownload'
import type { IgnorePatternItem, JobRecord, JobStatus } from '../types/api'

const { t } = useI18n()

const selectedFile = ref<File | null>(null)
const removeUnresolved = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
const cancelling = ref(false)
const deleting = ref(false)

const patternRows = ref<IgnorePatternItem[]>([])
const savingPatterns = ref(false)
const patternsSaved = ref(false)

const jobs = ref<JobRecord[]>([])
const activeJobId = ref<string | null>(null)
const activeJob = computed(() => jobs.value.find(j => j.job_id === activeJobId.value) || null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let saveTimer: ReturnType<typeof setTimeout> | null = null

function isTerminal(status: JobStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

function onFileSelected(file: File) {
  selectedFile.value = file
  error.value = null
}

function addRow() {
  patternRows.value.push({ field: '', pattern: '' })
}

function removeRow(index: number) {
  patternRows.value.splice(index, 1)
}

function collectPatterns(): IgnorePatternItem[] {
  return patternRows.value.filter(r => r.field.trim() !== '' || r.pattern.trim() !== '')
}

async function savePatterns() {
  savingPatterns.value = true
  patternsSaved.value = false
  try {
    await saveIgnorePatterns(collectPatterns())
    patternsSaved.value = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      patternsSaved.value = false
    }, 2000)
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      error.value = t('errors.' + e.error, e.data)
    } else if (e instanceof Error) {
      error.value = t('errors.network_error')
    } else {
      error.value = t('errors.unexpected_error')
    }
  } finally {
    savingPatterns.value = false
  }
}

async function handleProcess() {
  if (!selectedFile.value) return
  error.value = null
  submitting.value = true
  try {
    const res = await createSbomEnrichJob(
      selectedFile.value,
      removeUnresolved.value,
      collectPatterns(),
    )
    activeJobId.value = res.job_id
    await loadJobs()
    startPolling(res.job_id)
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      error.value = t('errors.' + e.error, e.data)
    } else if (e instanceof Error) {
      error.value = t('errors.network_error')
    } else {
      error.value = t('errors.unexpected_error')
    }
  } finally {
    submitting.value = false
  }
}

function startPolling(jobId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const record = await getJob(jobId)
      const idx = jobs.value.findIndex(j => j.job_id === jobId)
      if (idx >= 0) {
        jobs.value[idx] = record
      }
      if (isTerminal(record.status)) {
        stopPolling()
      }
    } catch {
      stopPolling()
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function selectJob(jobId: string) {
  activeJobId.value = jobId
  stopPolling()
  try {
    const record = await getJob(jobId)
    const idx = jobs.value.findIndex(j => j.job_id === jobId)
    if (idx >= 0) {
      jobs.value[idx] = record
    } else {
      jobs.value.unshift(record)
    }
    if (!isTerminal(record.status)) {
      startPolling(jobId)
    }
  } catch {
    // ignore
  }
}

async function handleCancel() {
  if (!activeJobId.value) return
  cancelling.value = true
  try {
    await cancelJob(activeJobId.value)
    await loadJobs()
  } catch {
    // ignore
  } finally {
    cancelling.value = false
  }
}

async function handleDelete() {
  if (!activeJobId.value) return
  deleting.value = true
  try {
    await deleteJob(activeJobId.value)
    jobs.value = jobs.value.filter(j => j.job_id !== activeJobId.value)
    activeJobId.value = jobs.value.length > 0 ? jobs.value[0].job_id : null
  } catch {
    // ignore
  } finally {
    deleting.value = false
  }
}

async function loadJobs() {
  try {
    const data = await listJobs(20, 0)
    jobs.value = data.jobs
  } catch {
    // ignore
  }
}

function downloadResultUrl(): string {
  return activeJobId.value ? downloadJobResultUrl(activeJobId.value) : '#'
}

onMounted(async () => {
  try {
    const data = await getIgnorePatterns()
    patternRows.value = data.patterns.length > 0 ? data.patterns : [{ field: '', pattern: '' }]
  } catch {
    patternRows.value = [{ field: '', pattern: '' }]
  }
  await loadJobs()
})

onUnmounted(() => {
  stopPolling()
  if (saveTimer) clearTimeout(saveTimer)
})
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

.options-section {
  margin-top: 1rem;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  cursor: pointer;
  font-size: 0.95rem;
}

.checkbox-row input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
}

.card {
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 1.25rem;
  box-shadow: var(--color-card-shadow);
  margin-top: 1rem;
}

.card-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--color-muted-light);
  margin-bottom: 0.75rem;
}

.pattern-rows {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.pattern-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pattern-input {
  flex: 1;
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
}

.pattern-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.pattern-label {
  font-size: 0.85rem;
  color: var(--color-muted);
  white-space: nowrap;
}

.btn-delete {
  background: none;
  border: 1px solid var(--color-delete-border);
  color: var(--color-error);
  border-radius: var(--border-radius);
  padding: 0.4rem 0.6rem;
  cursor: pointer;
  font-size: 0.85rem;
  line-height: 1;
}

.btn-delete:hover {
  background: var(--color-delete-bg-hover);
}

.pattern-toolbar {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: var(--color-card-bg);
  color: var(--color-body-text);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--color-table-header-bg);
}

.toolbar {
  margin-top: 1rem;
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.toolbar button {
  padding: 0.75rem 1.5rem;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 1rem;
  cursor: pointer;
}

.toolbar button:hover {
  background: var(--color-primary-hover);
}

.toolbar button:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
}

.loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1rem;
  color: var(--color-muted);
}

.progress-text {
  font-size: 0.85rem;
  color: var(--color-muted-light);
}

.btn-cancel {
  margin-left: auto;
  padding: 0.4rem 0.8rem;
  background: var(--color-card-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error-border);
  border-radius: var(--border-radius);
  font-size: 0.85rem;
  cursor: pointer;
}

.btn-cancel:hover {
  background: var(--color-error-bg);
}

.btn-delete-job {
  padding: 0.75rem 1.5rem;
  background: var(--color-error);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 1rem;
  cursor: pointer;
}

.btn-delete-job:hover {
  opacity: 0.9;
}

.btn-delete-job:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-msg {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--border-radius);
  padding: 1rem;
  color: var(--color-error);
  margin-top: 1rem;
}

.info-msg {
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius);
  padding: 1rem;
  color: var(--color-muted);
  margin-top: 1rem;
}

.jobs-section {
  margin-top: 1.5rem;
}

.job-details {
  margin-top: 1rem;
}

.results {
  margin-top: 1.5rem;
}

.summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-item {
  flex: 0 0 auto;
  min-width: 100px;
  text-align: center;
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 1rem 1.25rem;
  box-shadow: var(--color-card-shadow);
}

.summary-value {
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.2;
}

.summary-label {
  font-size: 0.8rem;
  color: var(--color-muted);
  margin-top: 0.25rem;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  font-size: 0.6rem;
  border-radius: 50%;
  border: 1px solid var(--color-muted-light);
  color: var(--color-muted-light);

  position: relative;
  line-height: 1;
}

.info-icon:hover::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: #2d2d2d;
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  white-space: nowrap;
  z-index: 100;
  pointer-events: none;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.info-icon:hover::before {
  content: '';
  position: absolute;
  bottom: calc(100% + 2px);
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #2d2d2d;
  z-index: 100;
  pointer-events: none;
}

.summary-found .summary-value {
  color: var(--color-success);
}

.summary-not-found .summary-value {
  color: var(--color-error);
}

.summary-skipped .summary-value {
  color: var(--color-warning);
}

.summary-removed .summary-value {
  color: #b45309;
}

.summary-ignored .summary-value {
  color: var(--color-muted-light);
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-card-bg);
  border-radius: var(--border-radius-lg);
  overflow: hidden;
  box-shadow: var(--color-card-shadow);
}

th {
  background: var(--color-table-header-bg);
  font-size: 0.8rem;
  text-transform: uppercase;
  color: var(--color-muted-light);
}

th, td {
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--color-row-border);
}

.cell-purl {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
  font-size: 0.85rem;
}

.status-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: var(--border-radius-full);
  font-size: 0.8rem;
  font-weight: 500;
}

.status-found {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-not_found {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.status-removed {
  background: #fff7ed;
  color: #b45309;
}

.status-ignored {
  background: var(--color-table-header-bg);
  color: var(--color-muted-light);
}
</style>
