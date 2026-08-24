import { apiFetch } from './client'
import type { BatchResolveRequest, BatchResolveResponse } from '../types/api'

export function resolvePurls(body: BatchResolveRequest): Promise<BatchResolveResponse> {
  return apiFetch<BatchResolveResponse>('/api/v1/resolve/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
