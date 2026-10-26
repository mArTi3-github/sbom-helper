import { apiFetch } from './client'
import type {
  IgnorePatternItem,
  SbomFixOptions,
  SbomFixOptionsResponse,
  SbomFixResponse,
} from '../types/api'

export function getIgnorePatterns(): Promise<{ patterns: IgnorePatternItem[] }> {
  return apiFetch<{ patterns: IgnorePatternItem[] }>('/api/v1/sbom/ignore-patterns')
}

export function saveIgnorePatterns(patterns: IgnorePatternItem[]): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/api/v1/sbom/ignore-patterns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patterns }),
  })
}

export function fixSbom(file: File, options: SbomFixOptions): Promise<SbomFixResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('options', JSON.stringify(options))
  return apiFetch<SbomFixResponse>('/api/v1/sbom/fix', {
    method: 'POST',
    body: formData,
  })
}

export function getFixOptions(): Promise<SbomFixOptionsResponse> {
  return apiFetch<SbomFixOptionsResponse>('/api/v1/sbom/fix/options')
}

export function saveFixOptions(options: SbomFixOptions): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/api/v1/sbom/fix/options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ options }),
  })
}
