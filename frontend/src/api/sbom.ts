import { apiFetch } from './client'
import type { IgnorePatternItem, SbomResponse } from '../types/api'

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

export function resolveSbom(
  file: File,
  removeUnresolved: boolean,
  ignorePatterns: IgnorePatternItem[],
  signal?: AbortSignal,
): Promise<SbomResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (removeUnresolved) formData.append('remove_unresolved_no_subcomponents', 'true')
  if (ignorePatterns.length > 0) formData.append('ignore_patterns', JSON.stringify(ignorePatterns))
  return apiFetch<SbomResponse>('/api/v1/resolve/sbom', {
    method: 'POST',
    body: formData,
    signal,
  })
}
