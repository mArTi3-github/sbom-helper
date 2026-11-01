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

      <div class="group-card" data-group="basic">
        <div class="group-header">
          <label class="master-label">
            <input
              v-model="basicMaster"
              type="checkbox"
              class="master-checkbox"
              :indeterminate.prop="basicIndeterminate"
            />
            <span>{{ t('sbomFixer.groups.basic') }}</span>
          </label>
          <div class="group-actions">
            <button type="button" class="btn btn-small select-all" @click="basicMaster = true">{{ t('sbomFixer.selectAll') }}</button>
            <button type="button" class="btn btn-small clear-all" @click="basicMaster = false">{{ t('sbomFixer.clearAll') }}</button>
          </div>
        </div>
        <div class="group-options">
          <div
            v-for="rule in BASE_RULES"
            :key="rule.id"
            class="rule-row"
            :data-rule-row="rule.id"
          >
            <label class="rule-label">
              <input v-model="options[rule.key]" type="checkbox" :data-rule="rule.id" />
              <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
            </label>
            <template v-if="rule.id === 'set_spec_version'">
              <span class="spec-version-label">{{ t('sbomFixer.specVersion') }}</span>
              <input
                v-model="options.spec_version"
                type="text"
                class="spec-version-input"
                :aria-label="t('sbomFixer.specVersion')"
                :disabled="!options.set_spec_version"
              />
            </template>
            <template v-if="rule.id === 'add_manufacturer'">
              <span class="spec-version-label">{{ t('sbomFixer.manufacturer') }}</span>
              <input
                v-model="options.manufacturer"
                type="text"
                class="spec-version-input manufacturer-input"
                :aria-label="t('sbomFixer.manufacturer')"
                :disabled="!options.add_manufacturer"
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

      <div class="group-card" data-group="licenses">
        <div class="group-header">
          <label class="master-label">
            <input
              v-model="licensesMaster"
              type="checkbox"
              class="master-checkbox"
              :indeterminate.prop="licensesIndeterminate"
            />
            <span>{{ t('sbomFixer.groups.licenses') }}</span>
          </label>
          <div class="group-actions">
            <button type="button" class="btn btn-small select-all" @click="licensesMaster = true">{{ t('sbomFixer.selectAll') }}</button>
            <button type="button" class="btn btn-small clear-all" @click="licensesMaster = false">{{ t('sbomFixer.clearAll') }}</button>
          </div>
        </div>
        <div class="group-options">
          <div
            v-for="rule in LICENSES_RULES"
            :key="rule.id"
            class="rule-row"
            :data-rule-row="rule.id"
          >
            <label class="rule-label">
              <input v-model="options.licenses[rule.key]" type="checkbox" :data-rule="rule.id" />
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

      <div class="group-card optional-fields-card" data-group="optional-fields">
        <div class="group-header">
          <span class="optional-fields-title">{{ t('sbomFixer.optionalFields.title') }}</span>
          <button
            type="button"
            class="btn btn-primary analyze-button"
            data-action="analyze"
            :disabled="!selectedFile || analysisLoading"
            @click="handleAnalyze"
          >
            {{ analysisLoading ? t('sbomFixer.optionalFields.analyzing') : t('sbomFixer.optionalFields.analyze') }}
          </button>
        </div>
        <p class="optional-fields-description">{{ t('sbomFixer.optionalFields.description') }}</p>

        <div v-if="catalogFailed" class="catalog-warning">{{ t('sbomFixer.optionalFields.catalogLoadFailed') }}</div>

        <div v-if="analysis === null" class="optional-hint">
          {{ selectedFile ? t('sbomFixer.optionalFields.needAnalysis') : t('sbomFixer.optionalFields.needFile') }}
        </div>
        <template v-else>
          <div v-if="candidates.length === 0" class="optional-empty">
            {{ t('sbomFixer.optionalFields.empty') }}
          </div>
          <template v-else>
            <div class="optional-fields-actions">
              <button
                type="button"
                class="btn btn-small"
                data-action="select-all-fields"
                @click="selectAllCandidates"
              >
                {{ t('sbomFixer.selectAll') }}
              </button>
              <button
                type="button"
                class="btn btn-small"
                data-action="clear-all-fields"
                @click="clearAllCandidates"
              >
                {{ t('sbomFixer.clearAll') }}
              </button>
            </div>
            <table class="candidate-table">
              <thead>
                <tr>
                  <th></th>
                  <th>{{ t('sbomFixer.optionalFields.path') }}</th>
                  <th>{{ t('sbomFixer.optionalFields.occurrences') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="field in candidates" :key="field.path" :data-field="field.path">
                  <td>
                    <input
                      type="checkbox"
                      class="remove-field-checkbox"
                      :data-remove-field="field.path"
                      :checked="selectedRemoveFields.has(field.path)"
                      @change="onRemoveFieldToggle(field.path, $event)"
                    />
                  </td>
                  <td class="field-path">{{ field.path }}</td>
                  <td class="field-count" :data-count="field.count">{{ field.count }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </template>

        <details v-if="fieldCatalog" class="fstec-details" data-role="fstec-list">
          <summary>{{ t('sbomFixer.optionalFields.fstecTitle') }}</summary>
          <table class="fstec-table">
            <thead>
              <tr>
                <th>{{ t('sbomFixer.optionalFields.path') }}</th>
                <th>{{ t('sbomFixer.optionalFields.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="field in fieldCatalog.fstec_fields"
                :key="field.path"
                :data-fstec-path="field.path"
              >
                <td class="field-path">{{ field.path }}</td>
                <td class="field-status">{{ fstecStatusLabel(field) }}</td>
              </tr>
            </tbody>
          </table>
        </details>

        <div class="keep-list-block">
          <label class="keep-list-title" for="keep-list">{{ t('sbomFixer.optionalFields.keepTitle') }}</label>
          <textarea
            id="keep-list"
            v-model="keepText"
            data-role="keep-list"
            class="keep-list-textarea"
            rows="6"
          ></textarea>
          <div class="keep-list-hint">{{ t('sbomFixer.optionalFields.keepHint') }}</div>
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
            <tr v-for="stat in result.stats" :key="stat.rule_id + (stat.field ?? '')">
              <td>{{ statLabel(stat) }}</td>
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
                <td>{{ issueLabel(issue) }}</td>
                <td>{{ issue.path }}</td>
                <td>{{ issue.component ?? '' }}</td>
                <td>{{ issueDetails(issue) }}</td>
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
import { BASE_RULES, COMPONENTS_RULES, LICENSES_RULES } from './sbomFixerRules'
import { analyzeSbom, fixSbom, getFieldCatalog, getFixOptions, saveFixOptions } from '../api/sbom'
import { ApiError } from '../api/client'
import { useSettingsStore } from '../stores/useSettingsStore'
import { downloadJson } from '../composables/useDownload'
import type {
  FieldCatalogResponse,
  FstecField,
  OptionalFieldInfo,
  SbomFixIssue,
  SbomFixOptions,
  SbomFixResponse,
  SbomFixStat,
} from '../types/api'

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

const fieldCatalog = ref<FieldCatalogResponse | null>(null)
const catalogFailed = ref(false)
const analysis = ref<OptionalFieldInfo[] | null>(null)
const analysisLoading = ref(false)
const selectedRemoveFields = ref<Set<string>>(new Set())

function defaultFixOptions(): SbomFixOptions {
  return {
    reorder: true,
    set_spec_version: true,
    spec_version: '1.7',
    increment_version: true,
    add_timestamp: true,
    add_manufacturer: true,
    manufacturer: 'Positive Technologies',
    components: {
      filter_external_references: true,
      filter_properties: true,
      fill_missing_gost_properties: false,
    },
    licenses: {
      filter_non_proprietary: false,
      add_proprietary: false,
      remove_proprietary_source_references: false,
      add_patterns: [],
    },
    optional_fields: {
      keep: [],
    },
  }
}

const options = reactive<SbomFixOptions>(defaultFixOptions())

function applyOptions(next: SbomFixOptions): void {
  options.reorder = next.reorder
  options.set_spec_version = next.set_spec_version
  options.spec_version = next.spec_version
  options.increment_version = next.increment_version
  options.add_timestamp = next.add_timestamp
  options.add_manufacturer = next.add_manufacturer
  options.manufacturer = next.manufacturer
  options.components = { ...options.components, ...next.components }
  options.licenses = {
    filter_non_proprietary: next.licenses.filter_non_proprietary,
    add_proprietary: next.licenses.add_proprietary,
    remove_proprietary_source_references: next.licenses.remove_proprietary_source_references,
    add_patterns: [...(next.licenses.add_patterns ?? [])],
  }
  options.optional_fields = { ...options.optional_fields, ...(next.optional_fields ?? {}) }
}

function plainOptions(): SbomFixOptions {
  return JSON.parse(JSON.stringify(options)) as SbomFixOptions
}

const openHelpId = ref<string | null>(null)

function toggleHelp(id: string): void {
  openHelpId.value = openHelpId.value === id ? null : id
}

const baseValues = () => BASE_RULES.map((rule) => options[rule.key])
const componentValues = () => COMPONENTS_RULES.map((rule) => options.components[rule.key])

const basicMaster = computed({
  get: () => baseValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of BASE_RULES) options[rule.key] = value
  },
})
const basicIndeterminate = computed(() => !basicMaster.value && baseValues().some(Boolean))

const componentsMaster = computed({
  get: () => componentValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of COMPONENTS_RULES) options.components[rule.key] = value
  },
})
const componentsIndeterminate = computed(() => !componentsMaster.value && componentValues().some(Boolean))

const licenseValues = () => LICENSES_RULES.map((rule) => options.licenses[rule.key])

const licensesMaster = computed({
  get: () => licenseValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of LICENSES_RULES) options.licenses[rule.key] = value
  },
})
const licensesIndeterminate = computed(
  () => !licensesMaster.value && licenseValues().some(Boolean),
)

const candidates = computed(() =>
  (analysis.value ?? []).filter(
    (field) => field.status === 'additional' && !options.optional_fields.keep.includes(field.path),
  ),
)

const keepText = computed({
  get: () => options.optional_fields.keep.join('\n'),
  set: (value: string) => {
    options.optional_fields.keep = value
      .split('\n')
      .filter((line) => line.trim() !== '')
  },
})

watch(candidates, (list) => {
  const paths = new Set(list.map((field) => field.path))
  const kept = [...selectedRemoveFields.value].filter((path) => paths.has(path))
  if (kept.length !== selectedRemoveFields.value.size) {
    selectedRemoveFields.value = new Set(kept)
  }
})

function onRemoveFieldToggle(path: string, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked
  const next = new Set(selectedRemoveFields.value)
  if (checked) next.add(path)
  else next.delete(path)
  selectedRemoveFields.value = next
}

function selectAllCandidates(): void {
  selectedRemoveFields.value = new Set(candidates.value.map((field) => field.path))
}

function clearAllCandidates(): void {
  selectedRemoveFields.value = new Set()
}

const FSTEC_CONDITION_KEYS: Record<string, string> = {
  componentsPresent: 'sbomFixer.optionalFields.conditionComponentsPresent',
  sourceDistributionHashes: 'sbomFixer.optionalFields.conditionSourceDistributionHashes',
}

function fstecStatusLabel(field: FstecField): string {
  const base =
    field.status === 'mandatory'
      ? t('sbomFixer.optionalFields.fstecStatusMandatory')
      : t('sbomFixer.optionalFields.fstecStatusOptional')
  if (field.condition_key) {
    const key = FSTEC_CONDITION_KEYS[field.condition_key]
    if (key) return `${base} (${t(key)})`
  }
  return base
}

function statLabel(stat: SbomFixStat): string {
  if (stat.field) {
    return `${t('sbomFixer.optionalFields.remove')}: ${stat.field}`
  }
  return t('sbomFixer.rules.' + stat.rule_id)
}

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
  const keep = fieldCatalog.value?.default_keep ?? options.optional_fields.keep
  applyOptions(defaultFixOptions())
  options.optional_fields.keep = keep
  saveStatus.value = 'idle'
  saveError.value = null
}

function onFileSelected(file: File): void {
  selectedFile.value = file
  error.value = null
  result.value = null
  analysis.value = null
  selectedRemoveFields.value = new Set()
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

async function handleAnalyze(): Promise<void> {
  if (!selectedFile.value) return

  error.value = null
  result.value = null
  analysisLoading.value = true

  try {
    const response = await analyzeSbom(selectedFile.value)
    analysis.value = response.fields
    selectedRemoveFields.value = new Set()
  } catch (e: unknown) {
    analysis.value = null
    selectedRemoveFields.value = new Set()
    error.value = describeError(e)
  } finally {
    analysisLoading.value = false
  }
}

async function handleFix(): Promise<void> {
  if (!selectedFile.value) return

  error.value = null
  result.value = null
  loading.value = true

  try {
    result.value = await fixSbom(selectedFile.value, plainOptions(), [...selectedRemoveFields.value])
    statsOpen.value = true
    issuesOpen.value = false
  } catch (e: unknown) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const [optionsResult, settingsResult, catalogResult] = await Promise.allSettled([
    getFixOptions(),
    settingsStore.load(),
    getFieldCatalog(),
  ])
  if (optionsResult.status === 'fulfilled') {
    applyOptions(optionsResult.value.options)
  } else {
    optionsWarning.value = true
  }
  if (settingsResult.status === 'fulfilled') {
    downloadIndent.value = settingsStore.jsonIndent
  }
  if (catalogResult.status === 'fulfilled') {
    fieldCatalog.value = catalogResult.value
  } else {
    catalogFailed.value = true
  }
  if (optionsResult.status === 'rejected' && catalogResult.status === 'fulfilled') {
    options.optional_fields.keep = catalogResult.value.default_keep
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

.manufacturer-input {
  width: 12rem;
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
  overflow-y: auto;
  overflow-x: hidden;
}

.issues-table td {
  overflow-wrap: anywhere;
  word-break: break-word;
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

.optional-fields-title {
  font-weight: 600;
}

.optional-fields-description {
  color: var(--color-muted);
  font-size: 0.9rem;
  margin-top: 0.5rem;
  margin-bottom: 0.75rem;
}

.optional-hint,
.optional-empty {
  color: var(--color-muted);
  font-size: 0.9rem;
  margin-top: 0.75rem;
}

.optional-fields-actions {
  display: flex;
  gap: 0.5rem;
  margin: 0.5rem 0;
}

.candidate-table,
.fstec-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.5rem;
  font-size: 0.9rem;
}

.candidate-table th,
.candidate-table td,
.fstec-table th,
.fstec-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-row-border);
  vertical-align: top;
}

.candidate-table th,
.fstec-table th {
  color: var(--color-muted);
  font-weight: 600;
}

.field-path {
  font-family: var(--font-mono, monospace);
}

.field-count {
  width: 6rem;
}

.catalog-warning {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.12));
  border: 1px solid var(--color-warning, #f59e0b);
  border-radius: var(--border-radius);
  padding: 0.75rem 1rem;
  color: var(--color-warning, #b45309);
  margin-bottom: 0.75rem;
}

.fstec-details {
  margin-top: 1rem;
  border-top: 1px solid var(--color-row-border);
  padding-top: 0.75rem;
}

.fstec-details summary {
  cursor: pointer;
  font-weight: 600;
}

.keep-list-block {
  margin-top: 1rem;
  border-top: 1px solid var(--color-row-border);
  padding-top: 0.75rem;
}

.keep-list-title {
  display: block;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.keep-list-textarea {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-family: var(--font-mono, monospace);
  font-size: 0.9rem;
  resize: vertical;
}

.keep-list-hint {
  color: var(--color-muted);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}
</style>
