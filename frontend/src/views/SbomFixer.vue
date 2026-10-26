<template>
  <div class="container">
    <h1>{{ t('sbomFixer.title') }}</h1>
    <p class="subtitle">{{ t('sbomFixer.subtitle') }}</p>

    <div class="warning-banner">&#9888; {{ t('sbomFixer.warning') }}</div>

    <FileUploadZone accept=".json" :max-size="200" @file-selected="onFileSelected" />

    <div class="options-panel">
      <div class="options-toolbar">
        <button class="btn btn-primary save-settings" :disabled="saveStatus === 'saving'" @click="handleSave">
          {{ t('sbomFixer.saveSettings') }}
        </button>
        <span
          :class="['save-status', { 'save-status-saved': saveStatus === 'saved', 'save-status-error': saveStatus === 'error' }]"
        >
          <template v-if="saveStatus === 'saved'">{{ t('sbomFixer.saved') }}</template>
          <template v-else-if="saveStatus === 'error'">{{ saveError }}</template>
        </span>
        <button class="btn reset-defaults" @click="restoreDefaults">{{ t('sbomFixer.resetDefaults') }}</button>
      </div>

      <div v-if="optionsWarning" class="options-warning">{{ t('sbomFixer.loadFailed') }}</div>

      <div class="group-card" data-group="root">
        <div class="group-header">
          <label class="master-label">
            <input
              v-model="rootMaster"
              type="checkbox"
              class="master-checkbox"
              :indeterminate.prop="rootIndeterminate"
            />
            <span>{{ t('sbomFixer.groups.root') }}</span>
          </label>
          <div class="group-actions">
            <button type="button" class="btn btn-small select-all" @click="rootMaster = true">{{ t('sbomFixer.selectAll') }}</button>
            <button type="button" class="btn btn-small clear-all" @click="rootMaster = false">{{ t('sbomFixer.clearAll') }}</button>
          </div>
        </div>
        <div class="group-options">
          <label class="rule-row">
            <input v-model="options.root.reorder" type="checkbox" :data-rule="'root.reorder'" />
            <span>{{ t('sbomFixer.rules.root.reorder') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.root.set_spec_version" type="checkbox" :data-rule="'root.set_spec_version'" />
            <span>{{ t('sbomFixer.rules.root.set_spec_version') }}</span>
            <span class="spec-version-label">{{ t('sbomFixer.specVersion') }}</span>
            <input
              v-model="options.root.spec_version"
              type="text"
              class="spec-version-input"
              :disabled="!options.root.set_spec_version"
            />
          </label>
          <label class="rule-row">
            <input v-model="options.root.remove_dependencies" type="checkbox" :data-rule="'root.remove_dependencies'" />
            <span>{{ t('sbomFixer.rules.root.remove_dependencies') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.root.remove_services" type="checkbox" :data-rule="'root.remove_services'" />
            <span>{{ t('sbomFixer.rules.root.remove_services') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.root.increment_version" type="checkbox" :data-rule="'root.increment_version'" />
            <span>{{ t('sbomFixer.rules.root.increment_version') }}</span>
          </label>
        </div>
      </div>

      <div class="group-card" data-group="metadata">
        <div class="group-header">
          <label class="master-label">
            <input
              v-model="metadataMaster"
              type="checkbox"
              class="master-checkbox"
              :indeterminate.prop="metadataIndeterminate"
            />
            <span>{{ t('sbomFixer.groups.metadata') }}</span>
          </label>
          <div class="group-actions">
            <button type="button" class="btn btn-small select-all" @click="metadataMaster = true">{{ t('sbomFixer.selectAll') }}</button>
            <button type="button" class="btn btn-small clear-all" @click="metadataMaster = false">{{ t('sbomFixer.clearAll') }}</button>
          </div>
        </div>
        <div class="group-options">
          <label class="rule-row">
            <input v-model="options.metadata.add_timestamp" type="checkbox" :data-rule="'metadata.add_timestamp'" />
            <span>{{ t('sbomFixer.rules.metadata.add_timestamp') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.metadata.reorder" type="checkbox" :data-rule="'metadata.reorder'" />
            <span>{{ t('sbomFixer.rules.metadata.reorder') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.metadata.remove_properties" type="checkbox" :data-rule="'metadata.remove_properties'" />
            <span>{{ t('sbomFixer.rules.metadata.remove_properties') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.metadata.remove_tools" type="checkbox" :data-rule="'metadata.remove_tools'" />
            <span>{{ t('sbomFixer.rules.metadata.remove_tools') }}</span>
          </label>
        </div>

        <div class="subblock" data-group="metadata-component">
          <div class="group-header">
            <label class="master-label">
              <input
                v-model="metadataComponentMaster"
                type="checkbox"
                class="master-checkbox"
                :indeterminate.prop="metadataComponentIndeterminate"
              />
              <span>{{ t('sbomFixer.groups.metadataComponent') }}</span>
            </label>
            <div class="group-actions">
              <button type="button" class="btn btn-small select-all" @click="metadataComponentMaster = true">{{ t('sbomFixer.selectAll') }}</button>
              <button type="button" class="btn btn-small clear-all" @click="metadataComponentMaster = false">{{ t('sbomFixer.clearAll') }}</button>
            </div>
          </div>
          <div class="group-options">
            <label class="rule-row">
              <input v-model="options.metadata.component.reorder" type="checkbox" :data-rule="'metadata_component.reorder'" />
              <span>{{ t('sbomFixer.rules.metadata_component.reorder') }}</span>
            </label>
            <label class="rule-row">
              <input
                v-model="options.metadata.component.remove_external_references"
                type="checkbox"
                :data-rule="'metadata_component.remove_external_references'"
              />
              <span>{{ t('sbomFixer.rules.metadata_component.remove_external_references') }}</span>
            </label>
            <label class="rule-row">
              <input v-model="options.metadata.component.remove_properties" type="checkbox" :data-rule="'metadata_component.remove_properties'" />
              <span>{{ t('sbomFixer.rules.metadata_component.remove_properties') }}</span>
            </label>
            <label class="rule-row">
              <input v-model="options.metadata.component.remove_purl" type="checkbox" :data-rule="'metadata_component.remove_purl'" />
              <span>{{ t('sbomFixer.rules.metadata_component.remove_purl') }}</span>
            </label>
            <label class="rule-row">
              <input v-model="options.metadata.component.remove_scope" type="checkbox" :data-rule="'metadata_component.remove_scope'" />
              <span>{{ t('sbomFixer.rules.metadata_component.remove_scope') }}</span>
            </label>
            <label class="rule-row">
              <input v-model="options.metadata.component.rename_supplier" type="checkbox" :data-rule="'metadata_component.rename_supplier'" />
              <span>{{ t('sbomFixer.rules.metadata_component.rename_supplier') }}</span>
            </label>
          </div>
        </div>
      </div>

      <div class="group-card" data-group="components">
        <div class="group-header">
          <label class="master-label">
            <input
              v-model="componentsMaster"
              type="checkbox"
              class="master-checkbox"
              :indeterminate.prop="componentsIndeterminate"
            />
            <span>{{ t('sbomFixer.groups.components') }}</span>
          </label>
          <div class="group-actions">
            <button type="button" class="btn btn-small select-all" @click="componentsMaster = true">{{ t('sbomFixer.selectAll') }}</button>
            <button type="button" class="btn btn-small clear-all" @click="componentsMaster = false">{{ t('sbomFixer.clearAll') }}</button>
          </div>
        </div>
        <div class="group-options">
          <label class="rule-row">
            <input v-model="options.components.reorder" type="checkbox" :data-rule="'components.reorder'" />
            <span>{{ t('sbomFixer.rules.components.reorder') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.components.remove_hashes" type="checkbox" :data-rule="'components.remove_hashes'" />
            <span>{{ t('sbomFixer.rules.components.remove_hashes') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.components.remove_scope" type="checkbox" :data-rule="'components.remove_scope'" />
            <span>{{ t('sbomFixer.rules.components.remove_scope') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.components.filter_external_references" type="checkbox" :data-rule="'components.filter_external_references'" />
            <span>{{ t('sbomFixer.rules.components.filter_external_references') }}</span>
          </label>
          <label class="rule-row">
            <input v-model="options.components.filter_properties" type="checkbox" :data-rule="'components.filter_properties'" />
            <span>{{ t('sbomFixer.rules.components.filter_properties') }}</span>
          </label>
          <label class="rule-row">
            <input
              v-model="options.components.fill_missing_gost_properties"
              type="checkbox"
              :data-rule="'components.fill_missing_gost_properties'"
            />
            <span>{{ t('sbomFixer.rules.components.fill_missing_gost_properties') }}</span>
          </label>
        </div>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary fix-button" :disabled="!selectedFile || loading" @click="handleFix">
        {{ t('sbomFixer.fix') }}
      </button>
    </div>

    <div v-if="loading" class="loading">
      <span class="spinner"></span> {{ t('sbomFixer.processing') }}
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="result" class="results">
      <div :class="['status-card', result.changed ? 'status-changed' : 'status-unchanged']">
        <span v-if="result.changed">&#9888; {{ t('sbomFixer.changed') }}</span>
        <span v-else>&#10003; {{ t('sbomFixer.unchanged') }}</span>
      </div>

      <details class="stats-spoiler" :open="statsOpen" @toggle="onStatsToggle">
        <summary>{{ t('sbomFixer.statistics') }}</summary>
        <table class="stats-table">
          <thead>
            <tr>
              <th>{{ t('sbomFixer.rule') }}</th>
              <th>{{ t('sbomFixer.changes') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="stat in result.stats" :key="stat.rule_id">
              <td>{{ t('sbomFixer.rules.' + stat.rule_id) }}</td>
              <td class="stat-count">{{ stat.count }}</td>
            </tr>
          </tbody>
        </table>
      </details>

      <div v-if="result.issues.length === 0" class="no-issues-card">
        &#10003; {{ t('sbomFixer.noIssues') }}
      </div>
      <details v-else class="issues-spoiler" :open="issuesOpen" @toggle="onIssuesToggle">
        <summary>{{ t('sbomFixer.issuesToggle', { count: result.issues.length }) }}</summary>
        <div class="issues-table-wrapper">
          <table v-if="issuesOpen" class="issues-table">
            <thead>
              <tr>
                <th>{{ t('sbomFixer.issuesCode') }}</th>
                <th>{{ t('sbomFixer.issuesPath') }}</th>
                <th>{{ t('sbomFixer.issuesComponent') }}</th>
                <th>{{ t('sbomFixer.issuesDetails') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(issue, index) in result.issues" :key="index">
                <td class="issue-code" :title="issueLabel(issue)">{{ issueLabel(issue) }}</td>
                <td class="issue-path" :title="issue.path">{{ issue.path }}</td>
                <td class="issue-component" :title="issue.component ?? ''">{{ issue.component ?? '' }}</td>
                <td class="issue-details" :title="issueDetails(issue)">{{ issueDetails(issue) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <div class="download-toolbar">
        <button class="btn btn-primary download-button" @click="downloadResult">
          {{ t('sbomFixer.download') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import FileUploadZone from '../components/FileUploadZone.vue'
import { fixSbom, getFixOptions, saveFixOptions } from '../api/sbom'
import { ApiError } from '../api/client'
import { useSettingsStore } from '../stores/useSettingsStore'
import { downloadJson } from '../composables/useDownload'
import type { SbomFixIssue, SbomFixOptions, SbomFixResponse } from '../types/api'

const { t, te } = useI18n()

const settingsStore = useSettingsStore()

const selectedFile = ref<File | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<SbomFixResponse | null>(null)
const optionsWarning = ref(false)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const saveError = ref<string | null>(null)
const statsOpen = ref(true)
const issuesOpen = ref(false)
const downloadIndent = ref(4)
let changedWhileSaving = false

function defaultFixOptions(): SbomFixOptions {
  return {
    root: {
      reorder: true,
      set_spec_version: true,
      spec_version: '1.7',
      remove_dependencies: true,
      remove_services: true,
      increment_version: true,
    },
    metadata: {
      add_timestamp: true,
      reorder: true,
      remove_properties: true,
      remove_tools: true,
      component: {
        reorder: true,
        remove_external_references: true,
        remove_properties: true,
        remove_purl: false,
        remove_scope: true,
        rename_supplier: true,
      },
    },
    components: {
      reorder: true,
      remove_hashes: true,
      remove_scope: true,
      filter_external_references: true,
      filter_properties: true,
      fill_missing_gost_properties: false,
    },
  }
}

const options = reactive<SbomFixOptions>(defaultFixOptions())

function applyOptions(next: SbomFixOptions): void {
  options.root = { ...options.root, ...next.root }
  options.metadata = { ...options.metadata, ...next.metadata }
  options.metadata.component = { ...options.metadata.component, ...(next.metadata?.component ?? {}) }
  options.components = { ...options.components, ...next.components }
}

function plainOptions(): SbomFixOptions {
  return JSON.parse(JSON.stringify(options)) as SbomFixOptions
}

const rootKeys = [
  'reorder',
  'set_spec_version',
  'remove_dependencies',
  'remove_services',
  'increment_version',
] as const
const metadataKeys = ['add_timestamp', 'reorder', 'remove_properties', 'remove_tools'] as const
const metadataComponentKeys = [
  'reorder',
  'remove_external_references',
  'remove_properties',
  'remove_purl',
  'remove_scope',
  'rename_supplier',
] as const
const componentKeys = [
  'reorder',
  'remove_hashes',
  'remove_scope',
  'filter_external_references',
  'filter_properties',
  'fill_missing_gost_properties',
] as const

const rootValues = () => rootKeys.map((key) => options.root[key])
const metadataValues = () => [
  ...metadataKeys.map((key) => options.metadata[key]),
  ...metadataComponentKeys.map((key) => options.metadata.component[key]),
]
const metadataComponentValues = () => metadataComponentKeys.map((key) => options.metadata.component[key])
const componentValues = () => componentKeys.map((key) => options.components[key])

const rootMaster = computed({
  get: () => rootValues().every(Boolean),
  set: (value: boolean) => {
    for (const key of rootKeys) options.root[key] = value
  },
})
const rootIndeterminate = computed(() => !rootMaster.value && rootValues().some(Boolean))

const metadataMaster = computed({
  get: () => metadataValues().every(Boolean),
  set: (value: boolean) => {
    for (const key of metadataKeys) options.metadata[key] = value
    for (const key of metadataComponentKeys) options.metadata.component[key] = value
  },
})
const metadataIndeterminate = computed(() => !metadataMaster.value && metadataValues().some(Boolean))

const metadataComponentMaster = computed({
  get: () => metadataComponentValues().every(Boolean),
  set: (value: boolean) => {
    for (const key of metadataComponentKeys) options.metadata.component[key] = value
  },
})
const metadataComponentIndeterminate = computed(
  () => !metadataComponentMaster.value && metadataComponentValues().some(Boolean),
)

const componentsMaster = computed({
  get: () => componentValues().every(Boolean),
  set: (value: boolean) => {
    for (const key of componentKeys) options.components[key] = value
  },
})
const componentsIndeterminate = computed(() => !componentsMaster.value && componentValues().some(Boolean))

function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    return t('errors.' + e.error, e.data)
  }
  if (e instanceof Error) {
    return t('errors.network_error')
  }
  return t('errors.unexpected_error')
}

function issueLabel(issue: SbomFixIssue): string {
  const key = 'sbomFixer.issues.' + issue.code
  if (!te(key)) return issue.code
  const params: Record<string, unknown> = { ...issue.details }
  if (Array.isArray(params.missing)) {
    params.missing = params.missing.join(', ')
  }
  return t(key, params)
}

function issueDetails(issue: SbomFixIssue): string {
  const missing = issue.details?.missing
  if (Array.isArray(missing)) {
    return missing.join(', ')
  }
  return JSON.stringify(issue.details)
}

function onStatsToggle(event: Event): void {
  statsOpen.value = (event.target as HTMLDetailsElement).open
}

function onIssuesToggle(event: Event): void {
  issuesOpen.value = (event.target as HTMLDetailsElement).open
}

function downloadResult(): void {
  if (!result.value || !selectedFile.value) return
  downloadJson(
    result.value.fixed_sbom,
    selectedFile.value.name.replace(/\.json$/, '') + '_fixed.json',
    downloadIndent.value,
  )
}

watch(
  options,
  () => {
    if (saveStatus.value === 'saving') {
      changedWhileSaving = true
    } else {
      saveStatus.value = 'idle'
      saveError.value = null
    }
  },
  { deep: true },
)

function restoreDefaults(): void {
  applyOptions(defaultFixOptions())
  saveStatus.value = 'idle'
  saveError.value = null
}

function onFileSelected(file: File): void {
  selectedFile.value = file
  error.value = null
  result.value = null
  saveStatus.value = 'idle'
  saveError.value = null
}

async function handleSave(): Promise<void> {
  saveStatus.value = 'saving'
  saveError.value = null
  changedWhileSaving = false
  try {
    await saveFixOptions(plainOptions())
    saveStatus.value = changedWhileSaving ? 'idle' : 'saved'
  } catch (e: unknown) {
    saveError.value = describeError(e)
    saveStatus.value = 'error'
  }
}

async function handleFix(): Promise<void> {
  if (!selectedFile.value) return

  error.value = null
  result.value = null
  loading.value = true

  try {
    result.value = await fixSbom(selectedFile.value, plainOptions())
    statsOpen.value = true
    issuesOpen.value = false
  } catch (e: unknown) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const [optionsResult, settingsResult] = await Promise.allSettled([getFixOptions(), settingsStore.load()])
  if (optionsResult.status === 'fulfilled') {
    applyOptions(optionsResult.value.options)
  } else {
    optionsWarning.value = true
  }
  if (settingsResult.status === 'fulfilled') {
    downloadIndent.value = settingsStore.jsonIndent
  }
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

.warning-banner {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.12));
  border: 1px solid var(--color-warning, #f59e0b);
  border-radius: var(--border-radius);
  padding: 0.75rem 1rem;
  color: var(--color-warning, #b45309);
  margin-bottom: 1.5rem;
}

.options-panel {
  margin-top: 1.5rem;
}

.options-toolbar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.save-status {
  font-size: 0.9rem;
  min-width: 4rem;
  color: var(--color-muted);
}

.save-status-saved {
  color: var(--color-success);
}

.save-status-error {
  color: var(--color-error);
}

.options-warning {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.12));
  border: 1px solid var(--color-warning, #f59e0b);
  border-radius: var(--border-radius);
  padding: 0.75rem 1rem;
  color: var(--color-warning, #b45309);
  margin-bottom: 1rem;
}

.group-card {
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 1rem;
  margin-bottom: 1rem;
  box-shadow: var(--color-card-shadow);
}

.subblock {
  border-top: 1px solid var(--color-row-border);
  margin-top: 1rem;
  padding-top: 1rem;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.master-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  cursor: pointer;
}

.group-actions {
  display: flex;
  gap: 0.5rem;
}

.group-options {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  cursor: pointer;
}

.spec-version-label {
  margin-left: auto;
  color: var(--color-muted);
  font-size: 0.85rem;
}

.spec-version-input {
  width: 5rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  background: var(--color-input-bg);
  color: var(--color-text);
}

.spec-version-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-small {
  font-size: 0.8rem;
  padding: 0.25rem 0.6rem;
}

.toolbar {
  margin-top: 1rem;
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1rem;
  color: var(--color-muted);
}

.error-msg {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--border-radius);
  padding: 1rem;
  color: var(--color-error);
  margin-top: 1rem;
}

.results {
  margin-top: 1.5rem;
}

.status-card {
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 1rem;
  box-shadow: var(--color-card-shadow);
}

.status-changed {
  border-left: 4px solid var(--color-warning);
}

.status-unchanged {
  border-left: 4px solid var(--color-success);
}

.stats-spoiler,
.issues-spoiler {
  margin-top: 1rem;
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 0.75rem 1rem;
  box-shadow: var(--color-card-shadow);
}

.stats-spoiler summary,
.issues-spoiler summary {
  cursor: pointer;
  font-weight: 600;
}

.stats-table,
.issues-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.75rem;
  font-size: 0.9rem;
}

.stats-table th,
.stats-table td,
.issues-table th,
.issues-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-row-border);
  vertical-align: top;
}

.stats-table th,
.issues-table th {
  color: var(--color-muted);
  font-weight: 600;
}

.stat-count {
  width: 6rem;
}

.issues-table-wrapper {
  max-height: 24rem;
  overflow: auto;
}

.issues-table {
  table-layout: fixed;
}

.issues-table th,
.issues-table td {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.issue-code {
  width: 30%;
}

.issue-path {
  width: 25%;
}

.issue-component {
  width: 15%;
}

.issue-details {
  width: 30%;
}

.no-issues-card {
  margin-top: 1rem;
  background: var(--color-success-bg, rgba(16, 185, 129, 0.12));
  border: 1px solid var(--color-success);
  border-left: 4px solid var(--color-success);
  border-radius: var(--border-radius-lg);
  padding: 1rem;
  color: var(--color-success);
}

.download-toolbar {
  margin-top: 1rem;
  display: flex;
  gap: 0.5rem;
}
</style>
