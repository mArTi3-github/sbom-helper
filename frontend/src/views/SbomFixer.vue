<template>
  <div class="container">
    <h1>{{ t('sbomFixer.title') }}</h1>
    <p class="subtitle">{{ t('sbomFixer.subtitle') }}</p>

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
          <div
            v-for="rule in ROOT_RULES"
            :key="rule.id"
            class="rule-row"
            :data-rule-row="rule.id"
          >
            <label class="rule-label">
              <input v-model="options.root[rule.key]" type="checkbox" :data-rule="rule.id" />
              <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
            </label>
            <template v-if="rule.id === 'root.set_spec_version'">
              <span class="spec-version-label">{{ t('sbomFixer.specVersion') }}</span>
              <input
                v-model="options.root.spec_version"
                type="text"
                class="spec-version-input"
                :aria-label="t('sbomFixer.specVersion')"
                :disabled="!options.root.set_spec_version"
              />
            </template>
            <RuleHelp
              :rule-id="rule.id"
              :description="t(`sbomFixer.help.${rule.id}`)"
              :before="rule.example.before"
              :after="rule.example.after"
              :before-label="t('sbomFixer.exampleBefore')"
              :after-label="t('sbomFixer.exampleAfter')"
              :rule-title="t(`sbomFixer.rules.${rule.id}`)"
              :open="openHelpId === rule.id"
              @toggle="toggleHelp(rule.id)"
              @close="openHelpId = null"
            />
          </div>
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
          <div
            v-for="rule in METADATA_RULES"
            :key="rule.id"
            class="rule-row"
            :data-rule-row="rule.id"
          >
            <label class="rule-label">
              <input v-model="options.metadata[rule.key]" type="checkbox" :data-rule="rule.id" />
              <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
            </label>
            <RuleHelp
              :rule-id="rule.id"
              :description="t(`sbomFixer.help.${rule.id}`)"
              :before="rule.example.before"
              :after="rule.example.after"
              :before-label="t('sbomFixer.exampleBefore')"
              :after-label="t('sbomFixer.exampleAfter')"
              :rule-title="t(`sbomFixer.rules.${rule.id}`)"
              :open="openHelpId === rule.id"
              @toggle="toggleHelp(rule.id)"
              @close="openHelpId = null"
            />
          </div>
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
            <div
              v-for="rule in METADATA_COMPONENT_RULES"
              :key="rule.id"
              class="rule-row"
              :data-rule-row="rule.id"
            >
              <label class="rule-label">
                <input v-model="options.metadata.component[rule.key]" type="checkbox" :data-rule="rule.id" />
                <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
              </label>
              <RuleHelp
                :rule-id="rule.id"
                :description="t(`sbomFixer.help.${rule.id}`)"
                :before="rule.example.before"
                :after="rule.example.after"
                :before-label="t('sbomFixer.exampleBefore')"
                :after-label="t('sbomFixer.exampleAfter')"
                :rule-title="t(`sbomFixer.rules.${rule.id}`)"
                :open="openHelpId === rule.id"
                @toggle="toggleHelp(rule.id)"
                @close="openHelpId = null"
              />
            </div>
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
          <div
            v-for="rule in COMPONENTS_RULES"
            :key="rule.id"
            class="rule-row"
            :data-rule-row="rule.id"
          >
            <label class="rule-label">
              <input v-model="options.components[rule.key]" type="checkbox" :data-rule="rule.id" />
              <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
            </label>
            <RuleHelp
              :rule-id="rule.id"
              :description="t(`sbomFixer.help.${rule.id}`)"
              :before="rule.example.before"
              :after="rule.example.after"
              :before-label="t('sbomFixer.exampleBefore')"
              :after-label="t('sbomFixer.exampleAfter')"
              :rule-title="t(`sbomFixer.rules.${rule.id}`)"
              :open="openHelpId === rule.id"
              @toggle="toggleHelp(rule.id)"
              @close="openHelpId = null"
            />
          </div>
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
import RuleHelp from '../components/RuleHelp.vue'
import {
  COMPONENTS_RULES,
  METADATA_COMPONENT_RULES,
  METADATA_RULES,
  ROOT_RULES,
} from './sbomFixerRules'
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

const openHelpId = ref<string | null>(null)

function toggleHelp(id: string): void {
  openHelpId.value = openHelpId.value === id ? null : id
}

const rootValues = () => ROOT_RULES.map((rule) => options.root[rule.key])
const metadataValues = () => [
  ...METADATA_RULES.map((rule) => options.metadata[rule.key]),
  ...METADATA_COMPONENT_RULES.map((rule) => options.metadata.component[rule.key]),
]
const metadataComponentValues = () => METADATA_COMPONENT_RULES.map((rule) => options.metadata.component[rule.key])
const componentValues = () => COMPONENTS_RULES.map((rule) => options.components[rule.key])

const rootMaster = computed({
  get: () => rootValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of ROOT_RULES) options.root[rule.key] = value
  },
})
const rootIndeterminate = computed(() => !rootMaster.value && rootValues().some(Boolean))

const metadataMaster = computed({
  get: () => metadataValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of METADATA_RULES) options.metadata[rule.key] = value
    for (const rule of METADATA_COMPONENT_RULES) options.metadata.component[rule.key] = value
  },
})
const metadataIndeterminate = computed(() => !metadataMaster.value && metadataValues().some(Boolean))

const metadataComponentMaster = computed({
  get: () => metadataComponentValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of METADATA_COMPONENT_RULES) options.metadata.component[rule.key] = value
  },
})
const metadataComponentIndeterminate = computed(
  () => !metadataComponentMaster.value && metadataComponentValues().some(Boolean),
)

const componentsMaster = computed({
  get: () => componentValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of COMPONENTS_RULES) options.components[rule.key] = value
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
  flex-wrap: wrap;
}

.rule-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  cursor: pointer;
}

.spec-version-label {
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
