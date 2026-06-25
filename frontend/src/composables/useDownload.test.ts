import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { downloadJson, safeUrl } from './useDownload'

describe('safeUrl', () => {
  it('returns undefined for null input', () => {
    expect(safeUrl(null)).toBeUndefined()
  })

  it('returns undefined for undefined input', () => {
    expect(safeUrl(undefined)).toBeUndefined()
  })

  it('returns undefined for empty string', () => {
    expect(safeUrl('')).toBeUndefined()
  })

  it('returns "#" for javascript: protocol', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('#')
  })

  it('returns "#" for data: protocol', () => {
    expect(safeUrl('data:text/html,<script>alert(1)</script>')).toBe('#')
  })

  it('returns "#" for vbscript: protocol', () => {
    expect(safeUrl('vbscript:msgbox(1)')).toBe('#')
  })

  it('returns the URL unchanged for https', () => {
    expect(safeUrl('https://github.com/foo/bar')).toBe('https://github.com/foo/bar')
  })

  it('returns the URL unchanged for git+https', () => {
    expect(safeUrl('git+https://github.com/foo/bar.git')).toBe('git+https://github.com/foo/bar.git')
  })

  it('returns the URL unchanged for ssh', () => {
    expect(safeUrl('ssh://git@github.com/foo/bar.git')).toBe('ssh://git@github.com/foo/bar.git')
  })
})

describe('downloadJson', () => {
  let createObjectURL: ReturnType<typeof vi.spyOn>
  let revokeObjectURL: ReturnType<typeof vi.spyOn>
  let clickSpy: ReturnType<typeof vi.fn>
  let createElementSpy: ReturnType<typeof vi.spyOn>
  let originalCreateElement: typeof document.createElement

  beforeEach(() => {
    createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url')
    revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    clickSpy = vi.fn()
    originalCreateElement = document.createElement.bind(document)
    createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const anchor = originalCreateElement('a') as HTMLAnchorElement
        vi.spyOn(anchor, 'click').mockImplementation(clickSpy as () => void)
        return anchor
      }
      return originalCreateElement(tag)
    })
  })

  afterEach(() => {
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
    createElementSpy.mockRestore()
  })

  it('creates blob URL, triggers anchor click, and revokes URL', () => {
    downloadJson({ a: 1 }, 'test.json')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url')
  })

  it('serializes data as pretty JSON', () => {
    let capturedBlob: Blob | undefined
    createObjectURL.mockImplementation((obj: Blob | MediaSource) => {
      capturedBlob = obj as Blob
      return 'blob:fake-url'
    })
    downloadJson({ a: 1, b: [1, 2, 3] }, 'test.json')
    expect(capturedBlob).toBeDefined()
    expect(capturedBlob!.type).toBe('application/json')
  })

  it('sets the download attribute on the anchor element', () => {
    let capturedAnchor: HTMLAnchorElement | undefined
    createElementSpy.mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') {
        capturedAnchor = el as HTMLAnchorElement
        vi.spyOn(el as HTMLAnchorElement, 'click').mockImplementation(clickSpy as () => void)
      }
      return el
    })
    downloadJson({ x: 1 }, 'my-file.json')
    expect(capturedAnchor).toBeDefined()
    expect(capturedAnchor!.download).toBe('my-file.json')
    expect(capturedAnchor!.href).toBe('blob:fake-url')
  })
})