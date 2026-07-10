<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  accept?: string
  maxSize?: number
}>()

const hintText = computed(() => {
  const sizeMb = props.maxSize || 200
  const accept = (props.accept || '').toLowerCase()
  if (accept.includes('.csv')) return t('fileUpload.hintCsv', { sizeMb })
  if (accept.includes('.json')) return t('fileUpload.hintJson', { sizeMb })
  return t('fileUpload.hintDefault', { sizeMb })
})

const emit = defineEmits<{
  'file-selected': [file: File]
}>()

const selectedFile = ref<File | null>(null)
const errorMessage = ref<string | null>(null)
const isDragover = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragover.value = false
  const file = e.dataTransfer?.files[0]
  if (file) handleFile(file)
}

function onFileInput(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files?.length) handleFile(target.files[0])
}

function handleFile(file: File) {
  const maxBytes = (props.maxSize || 200) * 1048576
  if (file.size > maxBytes) {
    errorMessage.value = t('fileUpload.fileTooLarge', { maxSize: props.maxSize || 200 })
    return
  }
  errorMessage.value = null
  selectedFile.value = file
  emit('file-selected', file)
}

function openFileDialog() {
  fileInput.value?.click()
}
</script>

<template>
  <div
    class="upload-area"
    :class="{ dragover: isDragover }"
    @click="openFileDialog"
    @dragenter.prevent="isDragover = true"
    @dragover.prevent="isDragover = true"
    @dragleave.prevent="isDragover = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="fileInput"
      type="file"
      :accept="accept || '.json'"
      style="display: none"
      @change="onFileInput"
    />
    <div class="upload-label">
      <strong>{{ t('fileUpload.labelStrong') }}</strong> {{ t('fileUpload.labelOr') }}
    </div>
    <div class="upload-hint">{{ hintText }}</div>
    <div v-if="selectedFile" class="file-name">
      {{ t('fileUpload.file') }} {{ selectedFile.name }} ({{ formatSize(selectedFile.size) }})
    </div>
    <div v-if="errorMessage" class="error-msg">{{ errorMessage }}</div>
  </div>
</template>

<style scoped>
.upload-area {
  background: #fff;
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 2rem;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
}
.upload-area:hover,
.upload-area.dragover {
  border-color: #2563eb;
}
.upload-label {
  font-size: 1rem;
  color: #555;
  cursor: pointer;
}
.upload-label strong {
  color: #2563eb;
}
.upload-hint {
  font-size: 0.8rem;
  color: #999;
  margin-top: 0.5rem;
}
.file-name {
  font-size: 0.9rem;
  color: #555;
  margin-top: 0.5rem;
}
.error-msg {
  color: #b91c1c;
  font-size: 0.85rem;
  margin-top: 0.5rem;
}
</style>
