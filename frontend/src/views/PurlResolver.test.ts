import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import PurlResolver from './PurlResolver.vue'
import { ApiError } from '../api/client'
import type { BatchResolveResponse } from '../types/api'

const successResponse: BatchResolveResponse = {
  results: [
    {
      purl: 'pkg:pypi/requests@2.31.0',
      repository_url: 'https://github.com/psf/requests',
      warnings: [],
      resolver: 'purl2repo',
      found_by: 'purl2repo',
      resolved_at: '2026-06-25T10:00:00',
      error: null,
    },
  ],
}

const resolvePurlsMock = vi.fn()

vi.mock('../api/purl', () => ({
  resolvePurls: (body: { purls: string[] }) => resolvePurlsMock(body),
}))

function mountResolver() {
  return mountWithI18n(PurlResolver)
}

describe('PurlResolver.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resolvePurlsMock.mockResolvedValue(successResponse)
  })

  it('renders initial form without loading or results', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Resolve PURL')
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(true)
    expect(wrapper.find('.loading').exists()).toBe(false)
    expect(wrapper.find('.result-table').exists()).toBe(false)
    expect(wrapper.find('.error-msg').exists()).toBe(false)
  })

  it('calls resolvePurls with one PURL per line, trimmed and empty lines filtered', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('  pkg:pypi/requests@2.31.0  \n\npkg:pypi/flask@3.0.0\n  ')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(resolvePurlsMock).toHaveBeenCalledTimes(1)
    expect(resolvePurlsMock).toHaveBeenCalledWith({
      purls: ['pkg:pypi/requests@2.31.0', 'pkg:pypi/flask@3.0.0'],
    })
  })

  it('does not call the API when input contains only empty lines', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue(' \n\n ')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(resolvePurlsMock).not.toHaveBeenCalled()
  })

  it('renders a table with resolved rows', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const table = wrapper.find('.result-table')
    expect(table.exists()).toBe(true)
    const cells = table.findAll('tbody td')
    const rowText = table.find('tbody tr').text()
    expect(rowText).toContain('pkg:pypi/requests@2.31.0')
    expect(rowText).toContain('https://github.com/psf/requests')
    expect(rowText).toContain('purl2repo')
    expect(rowText).toContain('Resolved')
    expect(cells.length).toBe(6)
  })

  it('renders one row per result with status Not found', async () => {
    resolvePurlsMock.mockResolvedValueOnce({
      results: [
        successResponse.results[0],
        {
          purl: 'pkg:pypi/unknown@1.0.0',
          repository_url: null,
          warnings: ['No resolver found a repository URL'],
          resolver: '',
          found_by: '',
          resolved_at: '',
          error: null,
        },
      ],
    })
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0\npkg:pypi/unknown@1.0.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[1].text()).toContain('Not found')
  })

  it('renders error status for rows with an error', async () => {
    resolvePurlsMock.mockResolvedValueOnce({
      results: [
        {
          purl: 'not-a-purl',
          repository_url: null,
          warnings: [],
          resolver: '',
          found_by: '',
          resolved_at: '',
          error: 'invalid_purl',
        },
      ],
    })
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('not-a-purl')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const rowText = wrapper.find('tbody tr').text()
    expect(rowText).toContain('Invalid PURL')
    expect(wrapper.find('.status-error').exists()).toBe(true)
  })

  it('shows API error message when resolvePurls rejects with ApiError', async () => {
    resolvePurlsMock.mockRejectedValueOnce(new ApiError(400, 'batch_too_large'))
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Too many PURLs in one request')
    expect(wrapper.find('.result-table').exists()).toBe(false)
  })

  it('shows network error message when resolvePurls rejects with generic Error', async () => {
    resolvePurlsMock.mockRejectedValueOnce(new Error('network down'))
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })

  it('clears previous results when a new request starts', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.result-table').exists()).toBe(true)

    resolvePurlsMock.mockRejectedValueOnce(new Error('network down'))
    await wrapper.find('textarea').setValue('pkg:pypi/other@1.0.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.result-table').exists()).toBe(false)
  })
})
