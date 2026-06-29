import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DatabaseAdmin from './DatabaseAdmin.vue'
import DbFilterPanel from '../components/db/DbFilterPanel.vue'
import DbDataTable from '../components/db/DbDataTable.vue'
import DbImportModal from '../components/db/DbImportModal.vue'
import { ApiError } from '../api/client'
import type { ResolveResponse, PurlListResponse } from '../types/api'

function makeRow(purl: string, overrides: Partial<ResolveResponse> = {}): ResolveResponse {
  return {
    purl,
    repository_url: `https://github.com/${purl.split('/')[1]}`,
    repository_type: 'github',
    repository_kind: 'source_code',
    confidence: 'high',
    evidence: [],
    warnings: [],
    version_reference: null,
    resolver: 'purl2repo',
    found_by: 'purl2repo',
    resolved_at: '2026-06-25T10:00:00',
    ...overrides,
  }
}

const rows = [
  makeRow('pkg:pypi/requests@2.31.0'),
  makeRow('pkg:pypi/flask@2.3.0', { confidence: 'medium' }),
  makeRow('pkg:pypi/numpy@1.25.0', { confidence: 'low', repository_url: null }),
]

const defaultListResponse: PurlListResponse = { rows, total: 3, page: 1, page_size: 50 }

const listPurlsMock = vi.fn()
const updatePurlMock = vi.fn()
const deletePurlsMock = vi.fn()
const importCsvMock = vi.fn()
const exportCsvMock = vi.fn()

vi.mock('../api/db', () => ({
  listPurls: (params: unknown) => listPurlsMock(params),
  updatePurl: (purl: string, body: unknown) => updatePurlMock(purl, body),
  deletePurls: (purls: string[]) => deletePurlsMock(purls),
  importCsv: (file: File, strategy: string) => importCsvMock(file, strategy),
  exportSelectedCsv: (purls: string[]) => exportCsvMock(purls),
}))

function mountAdmin() {
  return mount(DatabaseAdmin)
}

describe('DatabaseAdmin.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    listPurlsMock.mockResolvedValue(defaultListResponse)
    updatePurlMock.mockResolvedValue({ ok: true })
    deletePurlsMock.mockResolvedValue({ deleted: 1 })
    importCsvMock.mockResolvedValue({ imported: 2, skipped: 0, errors: [] })
    exportCsvMock.mockResolvedValue(new Blob(['csv'], { type: 'text/csv' }))
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  })

  it('loads rows on mount with default sort and page 1', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.page).toBe(1)
    expect(params.page_size).toBe(50)
    expect(params.sort_by).toBe('resolved_at')
    expect(params.sort_order).toBe('desc')
    expect(wrapper.findAll('tbody tr').length).toBe(3)
  })

  it('applies filters on Apply click and resets page to 1', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    const fp = wrapper.findComponent(DbFilterPanel)
    await fp.find('#search').setValue('requests')
    await fp.find('#resolver').setValue('purl2repo')
    await fp.findAll('.filter-actions button').find((b) => b.text() === 'Apply')!.trigger('click')
    await flushPromises()

    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.search).toBe('requests')
    expect(params.resolver).toBe('purl2repo')
    expect(params.page).toBe(1)
  })

  it('resets all filters on Reset click', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const fp = wrapper.findComponent(DbFilterPanel)
    await fp.find('#search').setValue('requests')
    await fp.find('#confidence').setValue('high')
    await fp.findAll('.filter-actions button').find((b) => b.text() === 'Reset')!.trigger('click')
    await flushPromises()

    expect((fp.find('#search').element as HTMLInputElement).value).toBe('')
    expect((fp.find('#confidence').element as HTMLSelectElement).value).toBe('')
    const params = listPurlsMock.mock.calls[listPurlsMock.mock.calls.length - 1][0] as Record<string, unknown>
    expect(params.search).toBeUndefined()
    expect(params.confidence).toBeUndefined()
    expect(params.sort_by).toBe('resolved_at')
    expect(params.sort_order).toBe('desc')
  })

  it('sorts by column header click and toggles order on second click', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    const dt = wrapper.findComponent(DbDataTable)
    const purlHeader = dt.findAll('th.col-sortable').find((th) => th.text().includes('PURL'))!
    await purlHeader.trigger('click')
    await flushPromises()
    let params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.sort_by).toBe('purl')
    expect(params.sort_order).toBe('asc')

    listPurlsMock.mockClear()
    await purlHeader.trigger('click')
    await flushPromises()
    params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.sort_by).toBe('purl')
    expect(params.sort_order).toBe('desc')
  })

  it('toggles individual row selection', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const firstRowCheckbox = dt.findAll('tbody tr input[type="checkbox"]')[0]
    await firstRowCheckbox.trigger('change')
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    expect(exportBtn.text()).toContain('(1)')
  })

  it('selects all rows when header checkbox is clicked', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const headerCheckbox = dt.find('thead input[type="checkbox"]')
    await headerCheckbox.setValue(true)
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    expect(exportBtn.text()).toContain('(3)')
  })

  it('shows empty row message when API returns no rows', async () => {
    listPurlsMock.mockResolvedValueOnce({ rows: [], total: 0, page: 1, page_size: 50 })
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.find('.empty-row').exists()).toBe(true)
    expect(wrapper.find('.empty-row').text()).toBe('No records found')
  })

  it('enters edit mode and saves change on Enter key', async () => {
    const wrapper = mountAdmin()
    await flushPromises()

    const dt = wrapper.findComponent(DbDataTable)
    const firstRow = dt.findAll('tbody tr')[0]
    const purlCell = firstRow.findAll('td')[1]
    await purlCell.trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    expect(editInput.exists()).toBe(true)
    await editInput.setValue('pkg:pypi/requests@2.32.0')
    await editInput.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(updatePurlMock).toHaveBeenCalledTimes(1)
    expect(updatePurlMock).toHaveBeenCalledWith('pkg:pypi/requests@2.31.0', { purl: 'pkg:pypi/requests@2.32.0' })
  })

  it('cancels edit mode on Escape key without saving', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const firstRow = dt.findAll('tbody tr')[0]
    await firstRow.findAll('td')[1].trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    await editInput.setValue('changed')
    await editInput.trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(updatePurlMock).not.toHaveBeenCalled()
    expect(dt.find('input.inline-edit').exists()).toBe(false)
  })

  it('saves inline edit on blur', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const firstRow = dt.findAll('tbody tr')[0]
    await firstRow.findAll('td')[1].trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    await editInput.setValue('pkg:pypi/new@1.0.0')
    await editInput.trigger('blur')
    await flushPromises()

    expect(updatePurlMock).toHaveBeenCalledTimes(1)
    expect(updatePurlMock).toHaveBeenCalledWith('pkg:pypi/requests@2.31.0', { purl: 'pkg:pypi/new@1.0.0' })
  })

  it('deletes a single row when confirm returns true', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const delBtn = dt.findAll('tbody tr')[0].findAll('button').find((b) => b.text() === 'Del')!
    await delBtn.trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(deletePurlsMock).toHaveBeenCalledTimes(1)
    expect(deletePurlsMock).toHaveBeenCalledWith(['pkg:pypi/requests@2.31.0'])
  })

  it('does not delete when confirm returns false', async () => {
    vi.mocked(window.confirm).mockReturnValueOnce(false)
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const delBtn = dt.findAll('tbody tr')[0].findAll('button').find((b) => b.text() === 'Del')!
    await delBtn.trigger('click')
    await flushPromises()

    expect(deletePurlsMock).not.toHaveBeenCalled()
  })

  it('bulk deletes selected rows', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const dt = wrapper.findComponent(DbDataTable)
    const rowCheckboxes = dt.findAll('tbody tr input[type="checkbox"]')
    await rowCheckboxes[0].setValue(true)
    await rowCheckboxes[1].setValue(true)
    await flushPromises()

    const bulkBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Delete Selected'))!
    await bulkBtn.trigger('click')
    await flushPromises()

    expect(deletePurlsMock).toHaveBeenCalledTimes(1)
    const deletedPurls = deletePurlsMock.mock.calls[0][0] as string[]
    expect(deletedPurls).toHaveLength(2)
    expect(deletedPurls).toContain('pkg:pypi/requests@2.31.0')
    expect(deletedPurls).toContain('pkg:pypi/flask@2.3.0')
  })

  it('exports selected rows as CSV and triggers download', async () => {
    const clickSpy = vi.fn()
    const originalCreate = document.createElement.bind(document)
    const createSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const anchor = originalCreate('a') as HTMLAnchorElement
        vi.spyOn(anchor, 'click').mockImplementation(clickSpy)
        return anchor
      }
      return originalCreate(tag)
    })

    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('tbody tr input[type="checkbox"]')[0].setValue(true)
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    await exportBtn.trigger('click')
    await flushPromises()

    expect(exportCsvMock).toHaveBeenCalledTimes(1)
    expect(exportCsvMock).toHaveBeenCalledWith(['pkg:pypi/requests@2.31.0'])
    expect(clickSpy).toHaveBeenCalled()
    createSpy.mockRestore()
  })

  it('imports CSV file with upsert strategy by default', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Import CSV'))!.trigger('click')
    await flushPromises()

    const file = new File(['purl,repository_url\npkg:pypi/x@1,https://github.com/x'], 'import.csv', { type: 'text/csv' })
    const importModal = wrapper.findComponent(DbImportModal)
    await importModal.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const uploadBtn = document.querySelector('.modal-body .toolbar button') as HTMLElement
    uploadBtn.click()
    await flushPromises()

    expect(importCsvMock).toHaveBeenCalledTimes(1)
    expect(importCsvMock).toHaveBeenCalledWith(file, 'upsert')
  })

  it('imports CSV file with skip_existing strategy when radio is changed', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Import CSV'))!.trigger('click')
    await flushPromises()

    const file = new File(['purl,repository_url\npkg:pypi/x@1,https://github.com/x'], 'import.csv', { type: 'text/csv' })
    const importModal = wrapper.findComponent(DbImportModal)
    await importModal.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const skipRadio = document.querySelector('input[type="radio"][value="skip_existing"]') as HTMLInputElement
    skipRadio.checked = true
    skipRadio.dispatchEvent(new Event('change'))
    await flushPromises()

    const uploadBtn = document.querySelector('.modal-body .toolbar button') as HTMLElement
    uploadBtn.click()
    await flushPromises()

    expect(importCsvMock).toHaveBeenCalled()
    const lastCallArgs = importCsvMock.mock.calls[importCsvMock.mock.calls.length - 1]
    expect(lastCallArgs[1]).toBe('skip_existing')
  })

  it('shows import error message on ApiError', async () => {
    importCsvMock.mockRejectedValueOnce(new ApiError(400, 'bad_csv', 'Malformed CSV'))
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Import CSV'))!.trigger('click')
    await flushPromises()
    const file = new File(['bad'], 'bad.csv', { type: 'text/csv' })
    const importModal = wrapper.findComponent(DbImportModal)
    await importModal.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    const uploadBtn = document.querySelector('.modal-body .toolbar button') as HTMLElement
    uploadBtn.click()
    await flushPromises()

    expect(document.querySelector('.modal-body .error-msg')).not.toBeNull()
    expect(document.body.textContent).toContain('Malformed CSV')
  })

  it('paginates to next page when Next button is clicked', async () => {
    listPurlsMock.mockResolvedValueOnce({ rows, total: 100, page: 1, page_size: 50 })
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    const dt = wrapper.findComponent(DbDataTable)
    const nextBtn = dt.findAll('.pagination-controls button').find((b) => b.text().includes('Next'))!
    await nextBtn.trigger('click')
    await flushPromises()

    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.page).toBe(2)
  })

  it('changes page size and resets page to 1', async () => {
    listPurlsMock.mockResolvedValueOnce({ rows, total: 100, page: 1, page_size: 50 })
    const wrapper = mountAdmin()
    await flushPromises()

    // navigate to page 2 first so the page reset on size change actually triggers a fetch
    const dt = wrapper.findComponent(DbDataTable)
    await dt.findAll('.pagination-controls button').find((b) => b.text().includes('Next'))!.trigger('click')
    await flushPromises()
    listPurlsMock.mockClear()

    const pageSizeSelect = dt.find('.pagination-size select')
    await pageSizeSelect.setValue('100')
    await flushPromises()

    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.page_size).toBe(100)
    expect(params.page).toBe(1)
  })

  it('shows API error message when listPurls rejects with ApiError', async () => {
    listPurlsMock.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Database unavailable'))
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Database unavailable')
  })

  it('shows network error message when listPurls rejects with generic Error', async () => {
    listPurlsMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })
})
