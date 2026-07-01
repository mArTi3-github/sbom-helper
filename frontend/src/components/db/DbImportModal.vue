<template>
  <ModalDialog :show="store.showImportModal" title="Import CSV" @close="store.closeImportModal()">
    <FileUploadZone accept=".csv" @file-selected="store.handleImportFile" />

    <details class="csv-ref">
      <summary>CSV Format Reference</summary>
      <div class="csv-ref-content">
        <p>The CSV file must have a header row. Comma (<code>,</code>) delimiter. UTF-8 encoding (BOM handled automatically).</p>
        <p>Required columns:</p>
        <ul><li><code>purl</code> — Package URL in format "scheme:type/namespace/name" (the part before "@"). The field "namespace" is optional</li><li><code>repository_url</code> — Repository URL</li></ul>
        <p>Optional columns:</p>
        <ul>
          <li><code>repository_type</code> — e.g. <code>github</code>, <code>gitlab</code></li>
          <li><code>repository_kind</code> — e.g. <code>source_code</code></li>
          <li><code>confidence</code> — <code>high</code>, <code>medium</code>, or <code>low</code></li>
          <li><code>version_reference</code> — version tag/branch/SHA</li>
          <li><code>resolver</code> — resolver name (default: <code>import-csv</code>)</li>
          <li><code>evidence</code> — JSON array, e.g. <code>["homepage","description"]</code></li>
          <li><code>warnings</code> — JSON array, e.g. <code>["low_confidence"]</code></li>
        </ul>
        <p>Example:</p>
        <pre>purl,repository_url,confidence,resolver
pkg:pypi/requests@2.31.0,https://github.com/psf/requests,high,import-csv
pkg:pypi/flask@2.3.0,https://github.com/pallets/flask,medium,import-csv</pre>
      </div>
    </details>

    <div class="import-strategy">
      <label class="radio-label"><input type="radio" v-model="store.importStrategy" value="upsert"> Overwrite existing</label>
      <label class="radio-label"><input type="radio" v-model="store.importStrategy" value="skip_existing"> Skip existing</label>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" :disabled="!store.importFile || store.importLoading" @click="store.handleImportUpload()">
        {{ store.importLoading ? 'Uploading...' : 'Upload' }}
      </button>
    </div>

    <div v-if="store.importLoading" class="loading"><span class="spinner"></span> Importing...</div>
    <div v-if="store.importError" class="error-msg">{{ store.importError }}</div>

    <div v-if="store.importResults" class="import-results">
      <div class="import-stat">Imported: <strong>{{ store.importResults.imported }}</strong></div>
      <div class="import-stat">Skipped: <strong>{{ store.importResults.skipped }}</strong></div>
      <div v-if="store.importResults.errors.length" class="import-errors">
        <div class="import-stat import-stat-error">Errors: <strong>{{ store.importResults.errors.length }}</strong></div>
        <ul><li v-for="err in store.importResults.errors" :key="err.row">Row {{ err.row }}: {{ err.error }}</li></ul>
      </div>
    </div>
  </ModalDialog>
</template>

<script setup lang="ts">
import { useDbAdminStore } from '../../stores/useDbAdminStore'
import ModalDialog from '../ModalDialog.vue'
import FileUploadZone from '../FileUploadZone.vue'

const store = useDbAdminStore()
</script>

<style scoped>
.csv-ref {
  margin: 1rem 0;
}

.csv-ref summary {
  cursor: pointer;
  color: var(--color-primary);
  font-size: 0.9rem;
}

.csv-ref-content {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--color-muted);
}

.csv-ref-content ul {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.csv-ref-content code {
  background: var(--color-table-header-bg);
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
}

.csv-ref-content pre {
  background: var(--color-table-header-bg);
  padding: 0.75rem;
  border-radius: var(--border-radius);
  overflow-x: auto;
  font-size: 0.82rem;
  margin-top: 0.5rem;
}

.import-strategy {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1rem 0;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  cursor: pointer;
}

.import-results {
  margin-top: 1rem;
  padding: 1rem;
  background: var(--color-table-header-bg);
  border-radius: var(--border-radius);
}

.import-stat {
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}

.import-stat-error {
  color: var(--color-error);
  margin-top: 0.5rem;
}

.import-errors ul {
  margin: 0.25rem 0 0 1.25rem;
  font-size: 0.85rem;
  color: var(--color-error);
}
</style>
