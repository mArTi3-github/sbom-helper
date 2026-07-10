import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import PurlResolver from './PurlResolver.vue'
import { ApiError } from '../api/client'
import type { ResolveResponse } from '../types/api'

const successResponse: ResolveResponse = {
  purl: 'pkg:pypi/requests@2.31.0',
  repository_url: 'https://github.com/psf/requests',
  repository_type: 'github',
  repository_kind: 'source_code',
  confidence: 'high',
  evidence: ['homepage', 'description'],
  warnings: [],
  version_reference: 'https://github.com/psf/requests/tree/v2.31.0',
  resolver: 'purl2repo',
  found_by: 'purl2repo',
  resolved_at: '2026-06-25T10:00:00',
}

const resolvePurlMock = vi.fn()

vi.mock('../api/purl', () => ({
  resolvePurl: (body: { purl: string }) => resolvePurlMock(body),
}))

function mountResolver() {
  return mountWithI18n(PurlResolver)
}

describe('PurlResolver.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resolvePurlMock.mockResolvedValue(successResponse)
  })

  it('renders initial form without loading or result', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('PURL Resolver')
    expect(wrapper.find('input[type="text"]').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(true)
    expect(wrapper.find('.loading').exists()).toBe(false)
    expect(wrapper.find('.result').exists()).toBe(false)
    expect(wrapper.find('.error-msg').exists()).toBe(false)
  })

  it('calls resolvePurl with the trimmed PURL on submit', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('  pkg:pypi/requests@2.31.0  ')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(resolvePurlMock).toHaveBeenCalledTimes(1)
    expect(resolvePurlMock).toHaveBeenCalledWith({ purl: 'pkg:pypi/requests@2.31.0' })
  })

  it('renders result card with repository URL on success', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    const repoLink = wrapper.find('.repo-url a')
    expect(repoLink.exists()).toBe(true)
    expect(repoLink.attributes('href')).toBe('https://github.com/psf/requests')
    expect(repoLink.text()).toBe('https://github.com/psf/requests')
  })

  it('toggles details section when Show details is clicked', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const toggle = wrapper.find('.details-toggle')
    expect(toggle.exists()).toBe(true)
    expect(wrapper.find('.details').exists()).toBe(false)

    await toggle.trigger('click')
    expect(wrapper.find('.details').exists()).toBe(true)
    const detailsText = wrapper.find('.details').text()
    expect(detailsText).toContain('Repository Type')
    expect(detailsText).toContain('github')
    expect(detailsText).toContain('Evidence')
    expect(detailsText).toContain('homepage')

    await toggle.trigger('click')
    expect(wrapper.find('.details').exists()).toBe(false)
  })

  it('shows API error message when resolvePurl rejects with ApiError', async () => {
    resolvePurlMock.mockRejectedValueOnce(new ApiError(404, 'not_found'))
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/missing@1.0.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Not found')
    expect(wrapper.find('.result').exists()).toBe(false)
  })

  it('shows network error message when resolvePurl rejects with generic Error', async () => {
    resolvePurlMock.mockRejectedValueOnce(new Error('network down'))
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })

  it('shows fallback "No repository URL found" when response has null repository_url', async () => {
    resolvePurlMock.mockResolvedValueOnce({
      ...successResponse,
      repository_url: null,
      confidence: null,
      repository_type: null,
      repository_kind: null,
      evidence: [],
      warnings: [],
      version_reference: null,
    })
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/missing@1.0.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.repo-url').text()).toContain('No repository URL found')
  })
})