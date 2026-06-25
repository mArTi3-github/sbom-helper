<template>
  <div class="db-admin">
    <h1>Database Admin</h1>
    <p class="subtitle">View, edit, filter, import, and export the resolved_purls table</p>

    <div class="card filter-panel">
      <div class="filter-row">
        <div class="filter-group">
          <label for="search">Search by PURL</label>
          <input id="search" v-model="search" type="text" placeholder="e.g. requests" @keyup.enter="applyFilters">
        </div>
        <div class="filter-group">
          <label for="resolver">Resolver</label>
          <select id="resolver" v-model="resolver">
            <option value="">Any</option>
            <option value="purl2repo">purl2repo</option>
          </select>
        </div>
        <div class="filter-group">
          <label for="confidence">Confidence</label>
          <select id="confidence" v-model="confidence">
            <option value="">Any</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </div>
        <div class="filter-group">
          <label for="date-from">Date From</label>
          <input id="date-from" v-model="dateFrom" type="date">
        </div>
        <div class="filter-group">
          <label for="date-to">Date To</label>
          <input id="date-to" v-model="dateTo" type="date">
        </div>
        <div class="filter-actions">
          <button class="btn btn-primary" @click="applyFilters" :disabled="loading">
            <span v-if="loading" class="spinner"></span>
            <span v-else>Apply</span>
          </button>
          <button class="btn btn-secondary" @click="resetFilters">Reset</button>
        </div>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn btn-secondary" :disabled="selectedRows.size === 0" @click="exportCsv">Export CSV ({{ selectedRows.size }})</button>
      <button class="btn btn-secondary" @click="showImportModal = true">Import CSV</button>
      <button class="btn btn-danger" :disabled="selectedRows.size === 0" @click="deleteSelected">
        Delete Selected ({{ selectedRows.size }})
      </button>
    </div>

    <div v-if="loading" class="loading">
      <span class="spinner"></span> Loading...
    </div>

    <div v-if="errorMessage" class="error-msg">{{ errorMessage }}</div>
    <div v-if="successMessage" class="success-msg">{{ successMessage }}</div>

    <div v-if="!loading" class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th class="col-check">
              <input type="checkbox" :checked="allSelected" :indeterminate="someSelected" @change="toggleSelectAll">
            </th>
            <th class="col-sortable" @click="setSort('purl')">
              PURL
              <span v-if="sortBy === 'purl'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th class="col-sortable" @click="setSort('repository_url')">
              Repository URL
              <span v-if="sortBy === 'repository_url'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th class="col-sortable" @click="setSort('resolver')">
              Resolver
              <span v-if="sortBy === 'resolver'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th class="col-sortable" @click="setSort('repository_type')">
              Type
              <span v-if="sortBy === 'repository_type'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th class="col-sortable" @click="setSort('repository_kind')">
              Kind
              <span v-if="sortBy === 'repository_kind'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th class="col-sortable" @click="setSort('confidence')">
              Confidence
              <span v-if="sortBy === 'confidence'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th class="col-sortable" @click="setSort('version_reference')">
              Version Ref
              <span v-if="sortBy === 'version_reference'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th>Evidence</th>
            <th>Warnings</th>
            <th class="col-sortable" @click="setSort('resolved_at')">
              Resolved At
              <span v-if="sortBy === 'resolved_at'" class="sort-indicator">{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
            </th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in allRows" :key="row.purl">
            <td class="col-check">
              <input type="checkbox" :checked="selectedRows.has(row.purl)" @change="toggleRow(row.purl)">
            </td>
            <td @dblclick="handleCellDblclick(row, 'purl', $event)">
              <div v-if="editingRow === row.purl">
                <input
                  ref="editInput"
                  v-model="editingValues.purl"
                  class="inline-edit"
                  @keydown="handleCellKeydown($event, row)"
                  @blur="saveEdit(row)"
                >
              </div>
              <span v-else>{{ row.purl }}</span>
            </td>
            <td @dblclick="handleCellDblclick(row, 'repository_url', $event)">
              <div v-if="editingRow === row.purl">
                <input
                  v-model="editingValues.repository_url"
                  class="inline-edit"
                  @keydown="handleCellKeydown($event, row)"
                  @blur="saveEdit(row)"
                >
              </div>
              <a
                v-else-if="row.repository_url"
                :href="safeUrl(row.repository_url)"
                target="_blank"
                class="repo-link"
                :title="row.repository_url"
              >{{ row.repository_url }}</a>
              <span v-else class="null-value">—</span>
            </td>
            <td>{{ row.resolver }}</td>
            <td>{{ row.repository_type || '—' }}</td>
            <td>{{ row.repository_kind || '—' }}</td>
            <td>
              <span v-if="row.confidence" :class="['badge', 'badge-' + row.confidence]">{{ row.confidence }}</span>
              <span v-else class="null-value">—</span>
            </td>
            <td>{{ row.version_reference || '—' }}</td>
            <td :title="joinArray(row.evidence)">
              {{ truncate(joinArray(row.evidence)) }}
            </td>
            <td :title="joinArray(row.warnings)">
              {{ truncate(joinArray(row.warnings)) }}
            </td>
            <td class="cell-nowrap">{{ formatDate(row.resolved_at) }}</td>
            <td class="col-actions">
              <button class="btn btn-sm btn-secondary" @click="startEdit(row)">Edit</button>
              <button class="btn btn-sm btn-danger" @click="deleteRow(row.purl)">Del</button>
            </td>
          </tr>
          <tr v-if="allRows.length === 0">
            <td colspan="12" class="empty-row">No records found</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination">
      <div class="pagination-info">
        Total: {{ total }} rows
      </div>
      <div class="pagination-controls">
        <button class="btn btn-sm" :disabled="page === 1" @click="goToPage(1)">&laquo; First</button>
        <button class="btn btn-sm" :disabled="page === 1" @click="goToPage(page - 1)">&lsaquo; Prev</button>

        <template v-for="(p, i) in visiblePages" :key="i">
          <span v-if="p === '...'" class="pagination-ellipsis">...</span>
          <button
            v-else
            :class="['btn', 'btn-sm', p === page ? 'btn-active' : '']"
            @click="goToPage(p as number)"
          >{{ p }}</button>
        </template>

        <button class="btn btn-sm" :disabled="page === totalPages" @click="goToPage(page + 1)">Next &rsaquo;</button>
        <button class="btn btn-sm" :disabled="page === totalPages" @click="goToPage(totalPages)">Last &raquo;</button>
      </div>
      <div class="pagination-size">
        <label>
          Per page:
          <select v-model.number="localPageSize" @change="onPageSizeChange">
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="200">200</option>
          </select>
        </label>
      </div>
    </div>

    <ModalDialog :show="showImportModal" title="Import CSV" @close="closeImportModal">
      <FileUploadZone accept=".csv" @file-selected="handleImportFile" />

      <details class="csv-ref">
        <summary>CSV Format Reference</summary>
        <div class="csv-ref-content">
          <p>The CSV file must have a header row. Supported columns:</p>
          <ul>
            <li><code>purl</code> (required) — Package URL</li>
            <li><code>repository_url</code> (optional) — Repository URL</li>
          </ul>
          <p>Example:</p>
          <pre>purl,repository_url
pkg:pypi/requests@2.31.0,https://github.com/psf/requests
pkg:pypi/flask@2.3.0,https://github.com/pallets/flask</pre>
        </div>
      </details>

      <div class="import-strategy">
        <label class="radio-label">
          <input type="radio" v-model="importStrategy" value="upsert">
          Upsert (overwrite existing)
        </label>
        <label class="radio-label">
          <input type="radio" v-model="importStrategy" value="skip_existing">
          Skip existing
        </label>
      </div>

      <div class="toolbar">
        <button class="btn btn-primary" :disabled="!importFile || importLoading" @click="handleImportUpload">
          {{ importLoading ? 'Uploading...' : 'Upload' }}
        </button>
      </div>

      <div v-if="importLoading" class="loading">
        <span class="spinner"></span> Importing...
      </div>

      <div v-if="importError" class="error-msg">{{ importError }}</div>

      <div v-if="importResults" class="import-results">
        <div class="import-stat">Imported: <strong>{{ importResults.imported }}</strong></div>
        <div class="import-stat">Skipped: <strong>{{ importResults.skipped }}</strong></div>
        <div v-if="importResults.errors.length" class="import-errors">
          <div class="import-stat import-stat-error">Errors: <strong>{{ importResults.errors.length }}</strong></div>
          <ul>
            <li v-for="err in importResults.errors" :key="err.row">
              Row {{ err.row }}: {{ err.error }}
            </li>
          </ul>
        </div>
      </div>
    </ModalDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { usePagination } from '../composables/usePagination'
import { listPurls, updatePurl, deletePurls, importCsv, exportSelectedCsv as apiExportCsv } from '../api/db'
import type { PurlListParams } from '../api/db'
import { ApiError } from '../api/client'
import { safeUrl } from '../composables/useDownload'
import type { ResolveResponse } from '../types/api'
import ModalDialog from '../components/ModalDialog.vue'
import FileUploadZone from '../components/FileUploadZone.vue'

const { page, pageSize, total, totalPages, goToPage, changePageSize } = usePagination()

const search = ref('')
const resolver = ref('')
const confidence = ref('')
const dateFrom = ref('')
const dateTo = ref('')

const sortBy = ref('resolved_at')
const sortOrder = ref('desc')

const allRows = ref<ResolveResponse[]>([])
const selectedRows = ref(new Set<string>())
const editingRow = ref<string | null>(null)
const editingValues = ref<{ purl?: string; repository_url?: string }>({})

const loading = ref(false)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)

const showImportModal = ref(false)
const importFile = ref<File | null>(null)
const importStrategy = ref<'upsert' | 'skip_existing'>('upsert')
const importResults = ref<{ imported: number; skipped: number; errors: { row: number; error: string }[] } | null>(null)
const importLoading = ref(false)
const importError = ref<string | null>(null)

const localPageSize = ref(50)

let successTimer: ReturnType<typeof setTimeout> | null = null

function showSuccess(msg: string) {
  if (successTimer) clearTimeout(successTimer)
  successMessage.value = msg
  successTimer = setTimeout(() => { successMessage.value = null }, 3000)
}

const allSelected = computed(() => allRows.value.length > 0 && selectedRows.value.size === allRows.value.length)
const someSelected = computed(() => selectedRows.value.size > 0 && selectedRows.value.size < allRows.value.length)

const visiblePages = computed(() => {
  const pages: (number | string)[] = []
  const tp = totalPages.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
    return pages
  }
  pages.push(1)
  if (page.value > 3) pages.push('...')
  const start = Math.max(2, page.value - 1)
  const end = Math.min(tp - 1, page.value + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (page.value < tp - 2) pages.push('...')
  pages.push(tp)
  return pages
})

function joinArray(arr: string[] | null | undefined): string {
  if (!arr || arr.length === 0) return '—'
  return arr.join('; ')
}

function truncate(val: string, max = 80): string {
  if (val.length <= max) return val
  return val.substring(0, max) + '...'
}

function formatDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

async function fetchData() {
  loading.value = true
  errorMessage.value = null
  try {
    const params: PurlListParams = {
      page: page.value,
      page_size: pageSize.value,
      search: search.value || undefined,
      resolver: resolver.value || undefined,
      confidence: confidence.value || undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    }
    const data = await listPurls(params)
    allRows.value = data.rows
    total.value = data.total
    selectedRows.value = new Set()
    editingRow.value = null
    editingValues.value = {}
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      errorMessage.value = e.message
    } else if (e instanceof Error) {
      errorMessage.value = 'Network error: could not reach the server.'
    } else {
      errorMessage.value = 'An unexpected error occurred.'
    }
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  fetchData()
}

function resetFilters() {
  search.value = ''
  resolver.value = ''
  confidence.value = ''
  dateFrom.value = ''
  dateTo.value = ''
  sortBy.value = 'resolved_at'
  sortOrder.value = 'desc'
  page.value = 1
  fetchData()
}

function setSort(column: string) {
  if (sortBy.value === column) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = column
    sortOrder.value = 'asc'
  }
  fetchData()
}

function toggleSelectAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) {
    selectedRows.value = new Set(allRows.value.map(r => r.purl))
  } else {
    selectedRows.value = new Set()
  }
}

function toggleRow(purl: string) {
  const newSet = new Set(selectedRows.value)
  if (newSet.has(purl)) {
    newSet.delete(purl)
  } else {
    newSet.add(purl)
  }
  selectedRows.value = newSet
}

function startEdit(row: ResolveResponse) {
  editingRow.value = row.purl
  editingValues.value = { purl: row.purl, repository_url: row.repository_url || '' }
}

function cancelEdit() {
  editingRow.value = null
  editingValues.value = {}
}

async function saveEdit(row: ResolveResponse) {
  if (editingRow.value !== row.purl) return
  const body: { purl?: string | null; repository_url?: string | null } = {}
  if (editingValues.value.purl !== undefined && editingValues.value.purl !== row.purl) {
    body.purl = editingValues.value.purl || null
  }
  if (editingValues.value.repository_url !== undefined && editingValues.value.repository_url !== (row.repository_url || '')) {
    body.repository_url = editingValues.value.repository_url || null
  }
  if (Object.keys(body).length === 0) {
    cancelEdit()
    return
  }
  try {
    await updatePurl(row.purl, body)
    cancelEdit()
    showSuccess('Record updated successfully')
    await fetchData()
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      errorMessage.value = e.message
    } else {
      errorMessage.value = 'Failed to update record'
    }
    cancelEdit()
  }
}

function handleCellDblclick(row: ResolveResponse, field: 'purl' | 'repository_url', event: MouseEvent) {
  startEdit(row)
  if (field === 'repository_url') {
    editingValues.value.repository_url = row.repository_url || ''
  }
  nextTick(() => {
    const target = event.target as HTMLElement
    const input = target.closest('td')?.querySelector('input')
    input?.focus()
    input?.select()
  })
}

function handleCellKeydown(event: KeyboardEvent, row: ResolveResponse) {
  if (event.key === 'Enter') {
    saveEdit(row)
  } else if (event.key === 'Escape') {
    cancelEdit()
  }
}

async function deleteRow(purl: string) {
  if (!confirm(`Delete record "${purl}"? This cannot be undone.`)) return
  try {
    await deletePurls([purl])
    showSuccess('Record deleted')
    await fetchData()
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      errorMessage.value = e.message
    } else {
      errorMessage.value = 'Failed to delete record'
    }
  }
}

async function deleteSelected() {
  const count = selectedRows.value.size
  if (count === 0) return
  if (!confirm(`Delete ${count} selected record(s)? This cannot be undone.`)) return
  try {
    await deletePurls(Array.from(selectedRows.value))
    showSuccess(`${count} record(s) deleted`)
    await fetchData()
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      errorMessage.value = e.message
    } else {
      errorMessage.value = 'Failed to delete records'
    }
  }
}

async function exportCsv() {
  if (selectedRows.value.size === 0) return
  try {
    const blob = await apiExportCsv(Array.from(selectedRows.value))
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'purls_export.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    showSuccess('CSV exported successfully')
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      errorMessage.value = e.message
    } else {
      errorMessage.value = 'Failed to export CSV'
    }
  }
}

function handleImportFile(file: File) {
  importFile.value = file
  importResults.value = null
}

async function handleImportUpload() {
  if (!importFile.value) return
  importLoading.value = true
  importResults.value = null
  try {
    const result = await importCsv(importFile.value, importStrategy.value)
    importResults.value = result
    await fetchData()
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      importError.value = e.message
    } else {
      importError.value = 'Failed to import CSV'
    }
  } finally {
    importLoading.value = false
  }
}

function closeImportModal() {
  showImportModal.value = false
  importFile.value = null
  importResults.value = null
  importError.value = null
}

function onPageSizeChange() {
  changePageSize(localPageSize.value)
}

watch(pageSize, (val) => {
  localPageSize.value = val
})

watch(page, () => {
  fetchData()
})

onMounted(() => {
  localPageSize.value = pageSize.value
  fetchData()
})
</script>

<style scoped>
.db-admin {
  max-width: 1400px;
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

.filter-panel {
  margin-bottom: 1rem;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.filter-group label {
  font-size: 0.8rem;
  color: var(--color-muted-light);
  text-transform: uppercase;
}

.filter-group input,
.filter-group select {
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  min-width: 140px;
}

.filter-group input:focus,
.filter-group select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.filter-actions {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
  padding-bottom: 1px;
}

.toolbar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.btn {
  padding: 0.5rem 1rem;
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  cursor: pointer;
  background: var(--color-card-bg);
  color: var(--color-body-text);
  transition: background 0.15s, border-color 0.15s;
  white-space: nowrap;
}

.btn:hover {
  background: var(--color-table-header-bg);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  background: var(--color-card-bg);
  color: var(--color-body-text);
}

.btn-danger {
  background: var(--color-danger);
  color: #fff;
  border-color: var(--color-danger);
}

.btn-danger:hover {
  background: var(--color-danger-hover);
}

.btn-sm {
  padding: 0.35rem 0.65rem;
  font-size: 0.85rem;
}

.btn-active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.btn-active:hover {
  background: var(--color-primary-hover);
}

.error-msg {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--border-radius);
  padding: 0.75rem 1rem;
  color: var(--color-error);
  margin-bottom: 1rem;
}

.success-msg {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
  border-radius: var(--border-radius);
  padding: 0.75rem 1rem;
  color: var(--color-success);
  margin-bottom: 1rem;
}

.table-wrapper {
  overflow-x: auto;
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--color-card-shadow);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  background: var(--color-table-header-bg);
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--color-muted-light);
  padding: 0.65rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-row-border);
  white-space: nowrap;
  user-select: none;
}

.col-sortable {
  cursor: pointer;
}

.col-sortable:hover {
  color: var(--color-body-text);
}

.sort-indicator {
  margin-left: 0.25rem;
  font-size: 0.7rem;
}

td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-row-border);
  font-size: 0.88rem;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

tr:last-child td {
  border-bottom: none;
}

tr:hover {
  background: rgba(0, 0, 0, 0.02);
}

.col-check {
  width: 40px;
  text-align: center;
}

.col-actions {
  white-space: nowrap;
  width: 120px;
}

.col-actions .btn + .btn {
  margin-left: 0.35rem;
}

.cell-nowrap {
  white-space: nowrap;
}

.repo-link {
  display: inline-block;
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.null-value {
  color: var(--color-muted-lighter);
}

.empty-row {
  text-align: center;
  padding: 2rem;
  color: var(--color-muted);
}

.inline-edit {
  width: 100%;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--border-radius);
  font-size: 0.88rem;
  box-sizing: border-box;
}

.inline-edit:focus {
  outline: none;
  box-shadow: 0 0 0 2px var(--color-primary-focus);
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 1rem;
  gap: 1rem;
  flex-wrap: wrap;
}

.pagination-info {
  font-size: 0.88rem;
  color: var(--color-muted);
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.pagination-ellipsis {
  padding: 0.35rem 0.25rem;
  color: var(--color-muted);
}

.pagination-size label {
  font-size: 0.88rem;
  color: var(--color-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pagination-size select {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.85rem;
}

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