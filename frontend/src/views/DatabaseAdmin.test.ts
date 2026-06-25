import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DatabaseAdmin from './DatabaseAdmin.vue'
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

    await wrapper.find('#search').setValue('requests')
    await wrapper.find('#resolver').setValue('purl2repo')
    await wrapper.findAll('.filter-actions button').find((b) => b.text() === 'Apply')!.trigger('click')
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
    await wrapper.find('#search').setValue('requests')
    await wrapper.find('#confidence').setValue('high')
    await wrapper.findAll('.filter-actions button').find((b) => b.text() === 'Reset')!.trigger('click')
    await flushPromises()

    expect((wrapper.find('#search').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('#confidence').element as HTMLSelectElement).value).toBe('')
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

    const purlHeader = wrapper.findAll('th.col-sortable').find((th) => th.text().includes('PURL'))!
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
    const firstRowCheckbox = wrapper.findAll('tbody tr input[type="checkbox"]')[0]
    await firstRowCheckbox.trigger('change')
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    expect(exportBtn.text()).toContain('(1)')
  })

  it('selects all rows when header checkbox is clicked', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const headerCheckbox = wrapper.find('thead input[type="checkbox"]')
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

    const firstRow = wrapper.findAll('tbody tr')[0]
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
    const firstRow = wrapper.findAll('tbody tr')[0]
    await firstRow.findAll('td')[1].trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    await editInput.setValue('changed')
    await editInput.trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(updatePurlMock).not.toHaveBeenCalled()
    expect(wrapper.find('input.inline-edit').exists()).toBe(false)
  })

  it('saves inline edit on blur', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const firstRow = wrapper.findAll('tbody tr')[0]
    await firstRow.findAll('td')[1].trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    await editInput.setValue('pkg:pypi/new@1.0.0')
    await editInput.trigger('blur')
    await flushPromises()

    expect(updatePurlMock).toHaveBeenCalledTimes(1)
    expect(updatePurlMock).toHaveBeenCalledWith('pkg:pypi/requests@2.31.0', { purl: 'pkg:pypi/new@1.0.0' })
  })
})