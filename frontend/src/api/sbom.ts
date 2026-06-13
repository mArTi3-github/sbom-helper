import { request } from './client'
import type { IgnorePatternItem, SbomResponse } from '../types/api'

export function getIgnorePatterns(): Promise<{ patterns: IgnorePatternItem[] }> {
  return request<{ patterns: IgnorePatternItem[] }>('/api/v1/sbom/ignore-patterns')
}

export function saveIgnorePatterns(patterns: IgnorePatternItem[]): Promise<{ status: string }> {
  return request<{ status: string }>('/api/v1/sbom/ignore-patterns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patterns }),
  })
}

export function resolveSbom(
  file: File,
  removeUnresolved: boolean,
  validateRefs: boolean,
  ignorePatterns: IgnorePatternItem[],
  signal?: AbortSignal,
): Promise<SbomResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (removeUnresolved) formData.append('remove_unresolved_no_subcomponents', 'true')
  if (validateRefs) formData.append('validate_existing_refs', 'true')
  if (ignorePatterns.length > 0) {
    formData.append('ignore_patterns', JSON.stringify(ignorePatterns))
  }
  return request<SbomResponse>('/api/v1/resolve/sbom', {
    method: 'POST',
    body: formData,
    signal,
  })
}