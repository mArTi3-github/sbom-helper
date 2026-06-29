import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { listPurls, updatePurl, deletePurls, importCsv, exportSelectedCsv as apiExportCsv } from '../api/db'
import type { PurlListParams } from '../api/db'
import type { ResolveResponse, ImportResponse } from '../types/api'
import { ApiError } from '../api/client'

export const useDbAdminStore = defineStore('dbAdmin', () => {
  const search = ref('')
  const resolver = ref('')
  const confidence = ref('')
  const dateFrom = ref('')
  const dateTo = ref('')

  const sortBy = ref('resolved_at')
  const sortOrder = ref('desc')

  const page = ref(1)
  const pageSize = ref(50)
  const total = ref(0)
  const totalPages = computed(() => Math.ceil(total.value / pageSize.value) || 1)

  const rows = ref<ResolveResponse[]>([])
  const selectedPurls = ref(new Set<string>())
  const allSelected = computed(() => rows.value.length > 0 && selectedPurls.value.size === rows.value.length)
  const someSelected = computed(() => selectedPurls.value.size > 0 && selectedPurls.value.size < rows.value.length)

  const editingPurl = ref<string | null>(null)
  const editingValues = ref<{ purl?: string; repository_url?: string }>({})

  const showImportModal = ref(false)
  const importFile = ref<File | null>(null)
  const importStrategy = ref<'upsert' | 'skip_existing'>('upsert')
  const importResults = ref<ImportResponse | null>(null)
  const importLoading = ref(false)
  const importError = ref<string | null>(null)

  const loading = ref(false)
  const errorMessage = ref<string | null>(null)
  const successMessage = ref<string | null>(null)

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
      rows.value = data.rows
      total.value = data.total
      selectedPurls.value = new Set()
      editingPurl.value = null
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

  function applyFilters() { page.value = 1; fetchData() }

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

  function toggleSelectAll(checked: boolean) {
    selectedPurls.value = checked ? new Set(rows.value.map(r => r.purl)) : new Set()
  }

  function toggleRow(purl: string) {
    const next = new Set(selectedPurls.value)
    if (next.has(purl)) next.delete(purl)
    else next.add(purl)
    selectedPurls.value = next
  }

  function startEdit(row: ResolveResponse) {
    editingPurl.value = row.purl
    editingValues.value = { purl: row.purl, repository_url: row.repository_url || '' }
  }

  function cancelEdit() {
    editingPurl.value = null
    editingValues.value = {}
  }

  async function saveEdit(row: ResolveResponse) {
    if (editingPurl.value !== row.purl) return
    const body: { purl?: string | null; repository_url?: string | null } = {}
    if (editingValues.value.purl !== undefined && editingValues.value.purl !== row.purl) {
      body.purl = editingValues.value.purl || null
    }
    if (editingValues.value.repository_url !== undefined && editingValues.value.repository_url !== (row.repository_url || '')) {
      body.repository_url = editingValues.value.repository_url || null
    }
    if (Object.keys(body).length === 0) { cancelEdit(); return }
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

  async function deleteRow(purl: string) {
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
    const count = selectedPurls.value.size
    if (count === 0) return
    try {
      await deletePurls(Array.from(selectedPurls.value))
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
    if (selectedPurls.value.size === 0) return null
    try {
      const blob = await apiExportCsv(Array.from(selectedPurls.value))
      showSuccess('CSV exported successfully')
      return blob
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        errorMessage.value = e.message
      } else {
        errorMessage.value = 'Failed to export CSV'
      }
      return null
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
    importError.value = null
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

  function goToPage(p: number) {
    if (p < 1 || p > totalPages.value) return
    page.value = p
    fetchData()
  }

  function changePageSize(size: number) {
    pageSize.value = size
    page.value = 1
    fetchData()
  }

  function showSuccess(msg: string) {
    successMessage.value = msg
    setTimeout(() => { successMessage.value = null }, 3000)
  }

  return {
    search, resolver, confidence, dateFrom, dateTo,
    sortBy, sortOrder,
    page, pageSize, total, totalPages,
    rows, selectedPurls, allSelected, someSelected,
    editingPurl, editingValues,
    showImportModal, importFile, importStrategy, importResults, importLoading, importError,
    loading, errorMessage, successMessage,
    fetchData, applyFilters, resetFilters, setSort,
    toggleSelectAll, toggleRow, startEdit, cancelEdit, saveEdit,
    deleteRow, deleteSelected, exportCsv,
    handleImportFile, handleImportUpload, closeImportModal,
    goToPage, changePageSize,
  }
})
