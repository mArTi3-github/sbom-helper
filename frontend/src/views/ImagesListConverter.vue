<template>
  <div class="container">
    <h1>{{ t('imagesListConverter.title') }}</h1>
    <p class="subtitle">{{ t('imagesListConverter.subtitle') }}</p>

    <FileUploadZone accept=".json" @file-selected="onFileSelected" />

    <div class="toolbar">
      <button class="btn btn-primary" :disabled="!selectedFile || loading" @click="handleConvert">{{ t('imagesListConverter.convert') }}</button>
    </div>

    <div v-if="loading" class="loading">
      <span class="spinner"></span> {{ t('imagesListConverter.processing') }}
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="result" class="results">
      <div :class="['status-card', result.was_transformed ? 'status-transformed' : 'status-ok']">
        <span v-if="result.was_transformed">
          &#9888; {{ t('imagesListConverter.wasTransformed') }}
        </span>
        <span v-else>
          &#10003; {{ t('imagesListConverter.noTransformation') }}
        </span>
      </div>
      <div class="toolbar">
        <button class="btn btn-primary" @click="downloadResult">{{ t('imagesListConverter.downloadList') }}</button>
      </div>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>{{ t('imagesListConverter.imageName') }}</th>
              <th>{{ t('imagesListConverter.version') }}</th>
              <th>{{ t('imagesListConverter.componentsPopulated') }}</th>
              <th>{{ t('imagesListConverter.namePopulated') }}</th>
              <th>{{ t('imagesListConverter.propertiesPopulated') }}</th>
              <th>{{ t('imagesListConverter.duplicatesRemoved') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(img, i) in result.images" :key="i">
              <td>{{ img.name || '—' }}</td>
              <td>
                {{ img.version || '—' }}
                <span :class="img.missing_version ? 'flag-present' : 'flag-ok'">
                  {{ img.missing_version ? '\u2717' : '\u2713' }}
                </span>
              </td>
              <td>
                <span :class="img.missing_components ? 'flag-present' : 'flag-ok'">
                  {{ img.missing_components ? '\u2717' : '\u2713' }}
                </span>
              </td>
              <td>
                <span :class="img.missing_name ? 'flag-present' : 'flag-ok'">
                  {{ img.missing_name ? '\u2717' : '\u2713' }}
                </span>
              </td>
              <td>
                <span :class="img.missing_properties ? 'flag-present' : 'flag-ok'">
                  {{ img.missing_properties ? '\u2717' : '\u2713' }}
                </span>
              </td>
              <td>{{ img.duplicates_removed > 0 ? img.duplicates_removed : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import FileUploadZone from '../components/FileUploadZone.vue'
import { convertImagesList } from '../api/images'
import { ApiError } from '../api/client'
import { useSettingsStore } from '../stores/useSettingsStore'
import { downloadJson } from '../composables/useDownload'
import type { ImagesListResponse } from '../types/api'

const { t } = useI18n()

const selectedFile = ref<File | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<ImagesListResponse | null>(null)
const imagesListData = ref<unknown>(null)

function onFileSelected(file: File) {
  selectedFile.value = file
  error.value = null
  result.value = null
  imagesListData.value = null
}

async function handleConvert() {
  if (!selectedFile.value) return

  error.value = null
  result.value = null
  imagesListData.value = null
  loading.value = true

  try {
    const res = await convertImagesList(selectedFile.value)
    result.value = res
    imagesListData.value = res.images_list
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

function downloadResult() {
  if (!imagesListData.value || !selectedFile.value) return
  const store = useSettingsStore()
  downloadJson(imagesListData.value, selectedFile.value.name.replace(/\.json$/, '') + '_images_list.json', store.jsonIndent)
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

.status-ok {
  border-left: 4px solid var(--color-success);
}

.status-transformed {
  border-left: 4px solid var(--color-warning);
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
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

.flag-present {
  color: var(--color-error);
  font-weight: 500;
}

.flag-ok {
  color: var(--color-success);
  font-weight: 500;
}
</style>