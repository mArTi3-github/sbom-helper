import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { i18n } from '../tests/i18n'
import RecentJobs from './RecentJobs.vue'
import type { JobRecord } from '../types/api'

const mockJobs: JobRecord[] = [
  { job_id: '1', type: 'sbom_enrich', status: 'completed', progress_current: 0, progress_total: 0, progress_phase: null, input_filename: 'bom.json', summary: null, results: null, error_message: null, created_at: '2026-07-10T12:00:00', started_at: null, finished_at: null },
  { job_id: '2', type: 'sbom_enrich', status: 'running', progress_current: 5, progress_total: 10, progress_phase: null, input_filename: 'app.json', summary: null, results: null, error_message: null, created_at: '2026-07-10T12:05:00', started_at: null, finished_at: null },
]

function mountRecentJobs(props: { jobs: JobRecord[]; activeId: string | null }) {
  return mount(RecentJobs as any, {
    props,
    global: { plugins: [i18n] },
  })
}

describe('RecentJobs', () => {
  it('renders job rows', () => {
    const wrapper = mountRecentJobs({ jobs: mockJobs, activeId: null })
    expect(wrapper.findAll('.job-row').length).toBe(2)
  })

  it('highlights active job', () => {
    const wrapper = mountRecentJobs({ jobs: mockJobs, activeId: '1' })
    expect(wrapper.find('.job-active').exists()).toBe(true)
  })

  it('emits select on click', async () => {
    const wrapper = mountRecentJobs({ jobs: mockJobs, activeId: null })
    await wrapper.findAll('.job-row')[0].trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual(['1'])
  })

  it('shows empty state when no jobs', () => {
    const wrapper = mountRecentJobs({ jobs: [], activeId: null })
    expect(wrapper.text()).toContain('No recent jobs')
  })
})
