import { apiFetch } from './client'
import type { ResolveRequest, ResolveResponse } from '../types/api'

export function resolvePurl(body: ResolveRequest): Promise<ResolveResponse> {
  return apiFetch<ResolveResponse>('/api/v1/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
