<template>
  <div>
    <div class="toolbar">
      <button class="btn btn-primary" :disabled="store.addingNewRow" @click="store.startNewRow()">{{ t('dbAdmin.addRow') }}</button>
      <button class="btn btn-secondary" :disabled="store.selectedPurls.size === 0" @click="handleExport">{{ t('dbAdmin.exportCsv') }} ({{ store.selectedPurls.size }})</button>
      <button class="btn btn-secondary" @click="store.showImportModal = true">{{ t('dbAdmin.importCsv') }}</button>
      <button class="btn btn-danger" :disabled="store.selectedPurls.size === 0" @click="handleDeleteSelected">{{ t('dbAdmin.deleteSelected') }} ({{ store.selectedPurls.size }})</button>
    </div>

    <div v-if="store.loading" class="loading"><span class="spinner"></span> {{ t('dbAdmin.loading') }}</div>
    <div v-if="store.errorMessage" class="error-msg">{{ store.errorMessage }}</div>
    <div v-if="store.successMessage" class="success-msg">{{ store.successMessage }}</div>

    <div v-if="!store.loading" class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th class="col-check">
              <input type="checkbox" :checked="store.allSelected" :indeterminate="store.someSelected" @change="handleToggleAll">
            </th>
            <th class="col-sortable" @click="store.setSort('purl')">{{ t('dbAdmin.purl') }}<span v-if="store.sortBy === 'purl'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('repository_url')">{{ t('dbAdmin.repositoryUrl') }}<span v-if="store.sortBy === 'repository_url'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('resolver')">{{ t('dbAdmin.resolver') }}<span v-if="store.sortBy === 'resolver'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('resolved_at')">{{ t('dbAdmin.resolvedAt') }}<span v-if="store.sortBy === 'resolved_at'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th>{{ t('dbAdmin.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="store.addingNewRow" class="new-row">
            <td class="col-check"></td>
            <td>
              <input v-model="store.newRowValues.purl" class="inline-edit" placeholder="pkg:type/name" @keydown="handleNewRowKeydown">
            </td>
            <td>
              <input v-model="store.newRowValues.repository_url" class="inline-edit" placeholder="https://github.com/..." @keydown="handleNewRowKeydown">
            </td>
            <td><span class="auto-field">import-manual</span></td>
            <td class="cell-nowrap"><span class="auto-field">{{ currentTimestamp }}</span></td>
            <td class="col-actions">
              <button class="btn btn-sm btn-primary" :disabled="!store.newRowValues.purl || !store.newRowValues.repository_url" @click="store.saveNewRow()">{{ t('dbAdmin.saveNewRow') }}</button>
              <button class="btn btn-sm btn-secondary" @click="store.cancelNewRow()">{{ t('dbAdmin.cancelNewRow') }}</button>
            </td>
          </tr>
          <tr v-if="store.addingNewRow && store.newRowError" class="new-row-error">
            <td colspan="7"><span class="error-text">{{ store.newRowError }}</span></td>
          </tr>
          <tr v-for="row in store.rows" :key="row.purl">
            <td class="col-check"><input type="checkbox" :checked="store.selectedPurls.has(row.purl)" @change="store.toggleRow(row.purl)"></td>
            <td @dblclick="handleDblclick(row, 'purl', $event)">
              <div v-if="store.editingPurl === row.purl">
                <input ref="editInput" v-model="store.editingValues.purl" class="inline-edit" @keydown="handleKeydown($event, row)" @blur="store.saveEdit(row)">
              </div>
              <span v-else>{{ row.purl }}</span>
            </td>
            <td @dblclick="handleDblclick(row, 'repository_url', $event)">
              <div v-if="store.editingPurl === row.purl">
                <input v-model="store.editingValues.repository_url" class="inline-edit" @keydown="handleKeydown($event, row)" @blur="store.saveEdit(row)">
              </div>
              <a v-else-if="row.repository_url" :href="safeUrl(row.repository_url)" target="_blank" class="repo-link" :title="row.repository_url">{{ row.repository_url }}</a>
              <span v-else class="null-value">\u2014</span>
            </td>
            <td>{{ row.resolver }}</td>
            <td class="cell-nowrap">{{ formatDate(row.resolved_at) }}</td>
            <td class="col-actions">
              <button class="btn btn-sm btn-secondary" @click="store.startEdit(row)">{{ t('dbAdmin.edit') }}</button>
              <button class="btn btn-sm btn-danger" @click="handleDeleteRow(row.purl)">{{ t('dbAdmin.del') }}</button>
            </td>
          </tr>
          <tr v-if="store.rows.length === 0"><td colspan="7" class="empty-row">{{ t('dbAdmin.noRecords') }}</td></tr>
        </tbody>
      </table>
    </div>

    <div class="pagination">
      <div class="pagination-info">{{ t('dbAdmin.total') }} {{ store.total }} {{ t('dbAdmin.rows') }}</div>
      <div class="pagination-controls">
        <button class="btn btn-sm" :disabled="store.page === 1" @click="store.goToPage(1)">&laquo; {{ t('dbAdmin.first') }}</button>
        <button class="btn btn-sm" :disabled="store.page === 1" @click="store.goToPage(store.page - 1)">&lsaquo; {{ t('dbAdmin.prev') }}</button>
        <template v-for="(p, i) in visiblePages" :key="i">
          <span v-if="p === '...'" class="pagination-ellipsis">...</span>
          <button v-else :class="['btn', 'btn-sm', p === store.page ? 'btn-active' : '']" @click="store.goToPage(p as number)">{{ p }}</button>
        </template>
        <button class="btn btn-sm" :disabled="store.page === store.totalPages" @click="store.goToPage(store.page + 1)">{{ t('dbAdmin.next') }} &rsaquo;</button>
        <button class="btn btn-sm" :disabled="store.page === store.totalPages" @click="store.goToPage(store.totalPages)">{{ t('dbAdmin.last') }} &raquo;</button>
      </div>
      <div class="pagination-size">
        <label>{{ t('dbAdmin.perPage') }} <select v-model.number="localPageSize" @change="onPageSizeChange"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option><option :value="200">200</option></select></label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDbAdminStore } from '../../stores/useDbAdminStore'
import { safeUrl } from '../../composables/useDownload'
import type { ResolveResponse } from '../../types/api'

const { t } = useI18n()
const store = useDbAdminStore()
const localPageSize = ref(store.pageSize)

const visiblePages = computed(() => {
  const pages: (number | string)[] = []
  const tp = store.totalPages
  if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); return pages }
  pages.push(1)
  if (store.page > 3) pages.push('...')
  const start = Math.max(2, store.page - 1)
  const end = Math.min(tp - 1, store.page + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (store.page < tp - 2) pages.push('...')
  pages.push(tp)
  return pages
})

function formatDate(iso: string): string {
  if (!iso) return '\u2014'
  const d = new Date(iso)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function handleToggleAll(event: Event) {
  store.toggleSelectAll((event.target as HTMLInputElement).checked)
}

function handleDblclick(row: ResolveResponse, field: 'purl' | 'repository_url', event: MouseEvent) {
  store.startEdit(row)
  if (field === 'repository_url') store.editingValues.repository_url = row.repository_url || ''
  nextTick(() => {
    const target = event.target as HTMLElement
    const input = target.closest('td')?.querySelector('input')
    input?.focus()
    input?.select()
  })
}

const currentTimestamp = computed(() => {
  const d = new Date()
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

function handleNewRowKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && store.newRowValues.purl && store.newRowValues.repository_url) {
    store.saveNewRow()
  } else if (event.key === 'Escape') {
    store.cancelNewRow()
  }
}

function handleKeydown(event: KeyboardEvent, row: ResolveResponse) {
  if (event.key === 'Enter') store.saveEdit(row)
  else if (event.key === 'Escape') store.cancelEdit()
}

function handleDeleteRow(purl: string) {
  if (!confirm(t('dbAdmin.confirmDelete', { purl }))) return
  store.deleteRow(purl)
}

function handleDeleteSelected() {
  if (!confirm(t('dbAdmin.confirmDeleteSelected', { count: store.selectedPurls.size }))) return
  store.deleteSelected()
}

async function handleExport() {
  const blob = await store.exportCsv()
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'purls_export.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function onPageSizeChange() {
  store.changePageSize(localPageSize.value)
}

onMounted(() => {
  localPageSize.value = store.pageSize
  store.fetchData()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
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

.loading {
  margin-bottom: 1rem;
}

.table-wrapper {
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--color-card-shadow);
}

table {
  width: 100%;
  table-layout: fixed;
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
  word-break: break-word;
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
  overflow: visible;
  white-space: nowrap;
  width: 120px;
}

.col-actions .btn + .btn {
  margin-left: 0.35rem;
}

.cell-nowrap {
  word-break: break-word;
}

.repo-link {
  display: inline;
  word-break: break-all;
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

.new-row {
  background: rgba(59, 130, 246, 0.05);
}

.new-row td {
  border-top: 2px solid var(--color-primary);
}

.new-row-error td {
  padding-top: 0;
  padding-bottom: 0.75rem;
  border-bottom: none;
}

.error-text {
  color: var(--color-error);
  font-size: 0.82rem;
}

.auto-field {
  color: var(--color-muted);
  font-style: italic;
}
</style>
