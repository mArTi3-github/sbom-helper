import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ImagesListConverter from './ImagesListConverter.vue'
import { ApiError } from '../api/client'
import type { ImagesListResponse } from '../types/api'

const okResponse: ImagesListResponse = {
  was_transformed: false,
  images: [
    {
      name: 'nginx',
      version: '1.25.0',
      missing_components: false,
      missing_name: false,
      missing_version: false,
      missing_properties: false,
    },
    {
      name: 'redis',
      version: null,
      missing_components: true,
      missing_name: false,
      missing_version: true,
      missing_properties: false,
    },
  ],
  images_list: { images: [{ name: 'nginx', version: '1.25.0' }] },
}

const convertMock = vi.fn()

vi.mock('../api/images', () => ({
  convertImagesList: (file: File) => convertMock(file),
}))

function mountConverter() {
  return mount(ImagesListConverter)
}

describe('ImagesListConverter.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    convertMock.mockResolvedValue(okResponse)
  })

  it('renders initial empty state with disabled Convert button', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Images List Converter')
    const button = wrapper.find('.toolbar button')
    expect(button.exists()).toBe(true)
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.find('.results').exists()).toBe(false)
  })

  it('enables Convert button after file is selected and calls API', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    const uploadZone = wrapper.findComponent({ name: 'FileUploadZone' })
    await uploadZone.vm.$emit('file-selected', file)
    await flushPromises()

    const button = wrapper.find('.toolbar button')
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    await flushPromises()
    expect(convertMock).toHaveBeenCalledTimes(1)
    expect(convertMock).toHaveBeenCalledWith(file)
  })

  it('renders green status card when was_transformed is false', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    const statusCard = wrapper.find('.status-card')
    expect(statusCard.exists()).toBe(true)
    expect(statusCard.classes()).toContain('status-ok')
    expect(statusCard.text()).toContain('Преобразований не требуется')
  })

  it('renders yellow status card when was_transformed is true', async () => {
    convertMock.mockResolvedValueOnce({ ...okResponse, was_transformed: true })
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    const statusCard = wrapper.find('.status-card')
    expect(statusCard.classes()).toContain('status-transformed')
    expect(statusCard.text()).toContain('Выполнено преобразование')
  })

  it('renders images table with completeness flags', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('nginx')
    expect(rows[0].text()).toContain('1.25.0')
    expect(rows[1].text()).toContain('redis')
  })

  it('shows API error message on ApiError', async () => {
    convertMock.mockRejectedValueOnce(new ApiError(400, 'bad_request', 'Invalid SBOM'))
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Invalid SBOM')
    expect(wrapper.find('.results').exists()).toBe(false)
  })

  it('shows network error message on generic Error', async () => {
    convertMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })

  it('triggers JSON download when "Скачать список образов" is clicked', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clickSpy = vi.fn()
    const originalCreate = document.createElement.bind(document)
    const createSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const anchor = originalCreate('a') as HTMLAnchorElement
        vi.spyOn(anchor, 'click').mockImplementation(clickSpy as () => void)
        return anchor
      }
      return originalCreate(tag)
    })

    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()

    const buttons = wrapper.findAll('.toolbar button')
    const downloadBtn = buttons.find((b) => b.text().includes('Скачать'))
    expect(downloadBtn).toBeDefined()
    await downloadBtn!.trigger('click')

    expect(clickSpy).toHaveBeenCalled()
    expect(createObjectURL).toHaveBeenCalled()
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
    createSpy.mockRestore()
  })
})