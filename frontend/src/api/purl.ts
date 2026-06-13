import { request } from './client'
import type { ResolveRequest, ResolveResponse } from '../types/api'

export function resolvePurl(body: ResolveRequest): Promise<ResolveResponse> {
  return request<ResolveResponse>('/api/v1/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}