<template>
  <div class="container">
    <h1>Images List Converter</h1>
    <p class="subtitle">Загрузите CycloneDX SBOM (JSON), чтобы сформировать машиночитаемый список docker-образов продукта</p>

    <FileUploadZone accept=".json" @file-selected="onFileSelected" />

    <div class="toolbar">
      <button :disabled="!selectedFile || loading" @click="handleConvert">Конвертировать</button>
    </div>

    <div v-if="loading" class="loading">
      <span class="spinner"></span> Обработка SBOM...
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="result" class="results">
      <div :class="['status-card', result.was_transformed ? 'status-transformed' : 'status-ok']">
        <span v-if="result.was_transformed">
          &#9888; <strong>Выполнено преобразование</strong> — исходный SBOM был преобразован в список образов контейнеров.
        </span>
        <span v-else>
          &#10003; <strong>Преобразований не требуется</strong> — переданный файл уже является корректным списком образов.
        </span>
      </div>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Имя образа</th>
              <th>Версия</th>
              <th>Заполнены компоненты</th>
              <th>Заполнено поле name</th>
              <th>Заполнено поле Properties</th>
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
            </tr>
          </tbody>
        </table>
      </div>

      <div class="toolbar">
        <button @click="downloadResult">Скачать список образов</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import FileUploadZone from '../components/FileUploadZone.vue'
import { convertImagesList } from '../api/images'
import { ApiError } from '../api/client'
import { downloadJson } from '../composables/useDownload'
import type { ImagesListResponse } from '../types/api'

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
      error.value = e.message
    } else if (e instanceof Error) {
      error.value = 'Network error: could not reach the server.'
    } else {
      error.value = 'An unexpected error occurred.'
    }
  } finally {
    loading.value = false
  }
}

function downloadResult() {
  if (!imagesListData.value || !selectedFile.value) return
  downloadJson(imagesListData.value, selectedFile.value.name.replace(/\.json$/, '') + '_images_list.json')
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

button {
  padding: 0.75rem 1.5rem;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 1rem;
  cursor: pointer;
}

button:hover {
  background: var(--color-primary-hover);
}

button:disabled {
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

.spinner {
  display: inline-block;
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid #e5e7eb;
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.status-ok {
  border-left: 4px solid #166534;
}

.status-transformed {
  border-left: 4px solid #b45309;
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

th {
  background: #f9fafb;
  font-size: 0.8rem;
  text-transform: uppercase;
  color: #888;
}

th, td {
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.flag-present {
  color: #991b1b;
  font-weight: 500;
}

.flag-ok {
  color: #166534;
  font-weight: 500;
}
</style>