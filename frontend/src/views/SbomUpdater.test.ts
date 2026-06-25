import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SbomUpdater from './SbomUpdater.vue'
import { ApiError } from '../api/client'
import type { SbomResponse } from '../types/api'

const emptyPatterns = { patterns: [] }
const twoPatterns = { patterns: [{ field: 'purl', pattern: 'requests' }, { field: 'type', pattern: 'npm' }] }

const successResult: SbomResponse = {
  summary: {
    total_purls: 10,
    found: 7,
    not_found: 3,
    skipped: 0,
    removed: 0,
    ignored: 0,
  },
  results: [
    { purl: 'pkg:pypi/requests@2.31.0', status: 'found', repository_url: 'https://github.com/psf/requests', found_by: 'purl2repo', resolver: 'purl2repo' },
    { purl: 'pkg:pypi/missing@1.0.0', status: 'not_found', repository_url: null },
  ],
  enriched_sbom: { bomFormat: 'CycloneDX', components: [] },
}

const getIgnorePatternsMock = vi.fn()
const saveIgnorePatternsMock = vi.fn()
const resolveSbomMock = vi.fn()

vi.mock('../api/sbom', () => ({
  getIgnorePatterns: () => getIgnorePatternsMock(),
  saveIgnorePatterns: (patterns: unknown) => saveIgnorePatternsMock(patterns),
  resolveSbom: (file: File, removeUnresolved: boolean, validateRefs: boolean, patterns: unknown, signal: AbortSignal) =>
    resolveSbomMock(file, removeUnresolved, validateRefs, patterns, signal),
}))

function mountUpdater() {
  return mount(SbomUpdater)
}

describe('SbomUpdater.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getIgnorePatternsMock.mockResolvedValue(emptyPatterns)
    saveIgnorePatternsMock.mockResolvedValue({ status: 'ok' })
    resolveSbomMock.mockResolvedValue(successResult)
  })

  it('loads on mount with one empty pattern row when API returns empty', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    expect(getIgnorePatternsMock).toHaveBeenCalledTimes(1)
    const rows = wrapper.findAll('.pattern-row')
    expect(rows.length).toBe(1)
    const inputs = rows[0].findAll('input[type="text"]')
    expect((inputs[0].element as HTMLInputElement).value).toBe('')
    expect((inputs[1].element as HTMLInputElement).value).toBe('')
  })

  it('loads existing ignore patterns from API', async () => {
    getIgnorePatternsMock.mockResolvedValueOnce(twoPatterns)
    const wrapper = mountUpdater()
    await flushPromises()
    const rows = wrapper.findAll('.pattern-row')
    expect(rows.length).toBe(2)
    expect((rows[0].findAll('input[type="text"]')[0].element as HTMLInputElement).value).toBe('purl')
    expect((rows[0].findAll('input[type="text"]')[1].element as HTMLInputElement).value).toBe('requests')
  })

  it('falls back to empty pattern row when getIgnorePatterns fails', async () => {
    getIgnorePatternsMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = mountUpdater()
    await flushPromises()
    expect(wrapper.findAll('.pattern-row').length).toBe(1)
  })

  it('adds a new empty pattern row when "Добавить строку" is clicked', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const addBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Добавить'))
    await addBtn!.trigger('click')
    expect(wrapper.findAll('.pattern-row').length).toBe(2)
  })

  it('removes a pattern row when ✕ button is clicked', async () => {
    const twoPatternsFresh = { patterns: [{ field: 'purl', pattern: 'requests' }, { field: 'type', pattern: 'npm' }] }
    getIgnorePatternsMock.mockResolvedValueOnce(twoPatternsFresh)
    const wrapper = mountUpdater()
    await flushPromises()
    expect(wrapper.findAll('.pattern-row').length).toBe(2)
    const removeBtn = wrapper.find('.btn-delete')
    await removeBtn.trigger('click')
    expect(wrapper.findAll('.pattern-row').length).toBe(1)
  })

  it('saves only non-empty pattern rows', async () => {
    vi.useFakeTimers()
    try {
      const twoPatternsFresh = { patterns: [{ field: 'purl', pattern: 'requests' }, { field: 'type', pattern: 'npm' }] }
      getIgnorePatternsMock.mockResolvedValueOnce(twoPatternsFresh)
      const wrapper = mountUpdater()
      await flushPromises()
      const addBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Добавить'))
      await addBtn!.trigger('click')
      await flushPromises()

      const saveBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Сохранить'))
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveIgnorePatternsMock).toHaveBeenCalledTimes(1)
      expect(saveIgnorePatternsMock).toHaveBeenCalledWith([
        { field: 'purl', pattern: 'requests' },
        { field: 'type', pattern: 'npm' },
      ])
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows error message when saveIgnorePatterns fails with ApiError', async () => {
    saveIgnorePatternsMock.mockRejectedValueOnce(new ApiError(400, 'bad_request', 'Invalid pattern'))
    const wrapper = mountUpdater()
    await flushPromises()
    const saveBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Сохранить'))
    await saveBtn!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Invalid pattern')
  })

  it('processes SBOM and renders summary + results table', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const file = new File(['{}'], 'bom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Обработать'))
    expect(processBtn!.attributes('disabled')).toBeUndefined()
    await processBtn!.trigger('click')
    await flushPromises()

    expect(resolveSbomMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.results').exists()).toBe(true)
    expect(wrapper.text()).toContain('10')
    expect(wrapper.text()).toContain('7')
    expect(wrapper.text()).toContain('Not found')
    expect(wrapper.findAll('tbody tr').length).toBe(2)
  })

  it('passes an AbortSignal as the 5th argument to resolveSbom', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const file = new File(['{}'], 'bom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Обработать'))!.trigger('click')
    await flushPromises()

    const args = resolveSbomMock.mock.calls[0]
    expect(args.length).toBe(5)
    expect(args[4]).toBeInstanceOf(AbortSignal)
  })

  it('process button is disabled when no file is selected', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Обработать'))
    expect(processBtn!.attributes('disabled')).toBeDefined()
    await processBtn!.trigger('click')
    await flushPromises()
    expect(resolveSbomMock).not.toHaveBeenCalled()
  })
})