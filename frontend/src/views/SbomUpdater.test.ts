import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import SbomUpdater from './SbomUpdater.vue'
import { ApiError } from '../api/client'
import type { JobRecord } from '../types/api'

const emptyPatterns = { patterns: [] }
const twoPatterns = { patterns: [{ field: 'purl', pattern: 'requests' }, { field: 'type', pattern: 'npm' }] }

const runningJob: JobRecord = {
  job_id: 'job-1',
  type: 'sbom_enrich',
  status: 'running',
  progress_current: 5,
  progress_total: 10,
  input_filename: 'bom.json',
  summary: null,
  results: null,
  error_message: null,
  created_at: '2026-01-01T00:00:00Z',
  started_at: '2026-01-01T00:00:01Z',
  finished_at: null,
}

const completedJob: JobRecord = {
  job_id: 'job-2',
  type: 'sbom_enrich',
  status: 'completed',
  progress_current: 10,
  progress_total: 10,
  input_filename: 'bom.json',
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
  error_message: null,
  created_at: '2026-01-01T00:00:00Z',
  started_at: '2026-01-01T00:00:01Z',
  finished_at: '2026-01-01T00:01:00Z',
}

const failedJob: JobRecord = {
  job_id: 'job-3',
  type: 'sbom_enrich',
  status: 'failed',
  progress_current: 3,
  progress_total: 10,
  input_filename: 'bom.json',
  summary: null,
  results: null,
  error_message: 'Something went wrong',
  created_at: '2026-01-01T00:00:00Z',
  started_at: '2026-01-01T00:00:01Z',
  finished_at: '2026-01-01T00:00:30Z',
}

const getIgnorePatternsMock = vi.fn()
const saveIgnorePatternsMock = vi.fn()
const createSbomEnrichJobMock = vi.fn()
const getJobMock = vi.fn()
const cancelJobMock = vi.fn()
const deleteJobMock = vi.fn()
const listJobsMock = vi.fn()

vi.mock('../api/sbom', () => ({
  getIgnorePatterns: () => getIgnorePatternsMock(),
  saveIgnorePatterns: (patterns: unknown) => saveIgnorePatternsMock(patterns),
}))

vi.mock('../api/jobs', () => ({
  createSbomEnrichJob: (file: File, removeUnresolved: boolean, patterns: unknown) =>
    createSbomEnrichJobMock(file, removeUnresolved, patterns),
  getJob: (jobId: string) => getJobMock(jobId),
  cancelJob: (jobId: string) => cancelJobMock(jobId),
  deleteJob: (jobId: string) => deleteJobMock(jobId),
  listJobs: (limit: number, offset: number) => listJobsMock(limit, offset),
  downloadJobResultUrl: (jobId: string) => `/api/v1/jobs/${jobId}/result`,
}))

function mountUpdater() {
  return mountWithI18n(SbomUpdater)
}

describe('SbomUpdater.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getIgnorePatternsMock.mockResolvedValue(emptyPatterns)
    saveIgnorePatternsMock.mockResolvedValue({ status: 'ok' })
    createSbomEnrichJobMock.mockResolvedValue({ job_id: 'job-1', status: 'queued' })
    getJobMock.mockResolvedValue(completedJob)
    cancelJobMock.mockResolvedValue({ job_id: 'job-1', status: 'cancelled' })
    deleteJobMock.mockResolvedValue({ job_id: 'job-1', deleted: true })
    listJobsMock.mockResolvedValue({ jobs: [] })
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

  it('adds a new empty pattern row when "Add row" is clicked', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const addBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Add'))
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
      const addBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Add'))
      await addBtn!.trigger('click')
      await flushPromises()

      const saveBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Save'))
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
    saveIgnorePatternsMock.mockRejectedValueOnce(new ApiError(400, 'invalid_sbom'))
    const wrapper = mountUpdater()
    await flushPromises()
    const saveBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Save'))
    await saveBtn!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Invalid SBOM file')
  })

  it('creates an enrich job when Process is clicked', async () => {
    listJobsMock.mockResolvedValue({ jobs: [runningJob] })
    const wrapper = mountUpdater()
    await flushPromises()

    const file = new File(['{}'], 'bom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Process'))
    await processBtn!.trigger('click')
    await flushPromises()

    expect(createSbomEnrichJobMock).toHaveBeenCalledTimes(1)
    expect(listJobsMock).toHaveBeenCalled()
    expect(wrapper.find('.jobs-section').exists()).toBe(true)
  })

  it('renders completed job summary and results table', async () => {
    listJobsMock.mockResolvedValue({ jobs: [completedJob] })
    const wrapper = mountUpdater()
    await flushPromises()

    const jobRow = wrapper.find('.job-row')
    await jobRow.trigger('click')
    await flushPromises()

    expect(wrapper.find('.results').exists()).toBe(true)
    expect(wrapper.text()).toContain('10')
    expect(wrapper.text()).toContain('7')
    expect(wrapper.findAll('tbody tr').length).toBe(2)
  })

  it('cancels a running job', async () => {
    listJobsMock.mockResolvedValue({ jobs: [runningJob] })
    const wrapper = mountUpdater()
    await flushPromises()

    const jobRow = wrapper.find('.job-row')
    await jobRow.trigger('click')
    await flushPromises()

    const cancelBtn = wrapper.find('.btn-cancel')
    await cancelBtn.trigger('click')
    await flushPromises()

    expect(cancelJobMock).toHaveBeenCalledWith('job-1')
  })

  it('deletes a completed job', async () => {
    listJobsMock.mockResolvedValue({ jobs: [completedJob] })
    const wrapper = mountUpdater()
    await flushPromises()

    const jobRow = wrapper.find('.job-row')
    await jobRow.trigger('click')
    await flushPromises()

    const deleteBtn = wrapper.find('.btn-delete-job')
    await deleteBtn.trigger('click')
    await flushPromises()

    expect(deleteJobMock).toHaveBeenCalledWith('job-2')
  })

  it('process button is disabled when no file is selected', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Process'))
    expect(processBtn!.attributes('disabled')).toBeDefined()
    await processBtn!.trigger('click')
    await flushPromises()
    expect(createSbomEnrichJobMock).not.toHaveBeenCalled()
  })

  it('shows error when job creation fails with ApiError', async () => {
    createSbomEnrichJobMock.mockRejectedValueOnce(new ApiError(400, 'invalid_sbom'))
    const wrapper = mountUpdater()
    await flushPromises()

    const file = new File(['{}'], 'bom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Process'))
    await processBtn!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Invalid SBOM file')
  })

  it('shows failed job error message', async () => {
    listJobsMock.mockResolvedValue({ jobs: [failedJob] })
    const wrapper = mountUpdater()
    await flushPromises()

    const jobRow = wrapper.find('.job-row')
    await jobRow.trigger('click')
    await flushPromises()

    const errorMsg = wrapper.find('.error-msg')
    expect(errorMsg.exists()).toBe(true)
    expect(errorMsg.text()).toBe('Something went wrong')
  })
})
