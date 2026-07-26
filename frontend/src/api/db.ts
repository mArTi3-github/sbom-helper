import { apiFetch } from './client'
import type { PurlListResponse, PurlUpdateRequest, DeleteResponse, ImportResponse } from '../types/api'

export interface PurlListParams {
  page?: number
  page_size?: number
  search?: string
  resolver?: string
  date_from?: string
  date_to?: string
  sort_by?: string
  sort_order?: string
}

function buildPurlQuery(params: PurlListParams): URLSearchParams {
  const query = new URLSearchParams()
  if (params.page !== undefined) query.set('page', String(params.page))
  if (params.page_size !== undefined) query.set('page_size', String(params.page_size))
  if (params.search) query.set('search', params.search)
  if (params.resolver) query.set('resolver', params.resolver)
  if (params.date_from) query.set('date_from', params.date_from)
  if (params.date_to) query.set('date_to', params.date_to)
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.sort_order) query.set('sort_order', params.sort_order)
  return query
}

export function listPurls(params: PurlListParams): Promise<PurlListResponse> {
  const query = buildPurlQuery(params)
  return apiFetch<PurlListResponse>(`/api/v1/db/purls?${query.toString()}`)
}

export function updatePurl(purl: string, body: PurlUpdateRequest): Promise<{ ok: boolean }> {
  const encoded = encodeURIComponent(purl).replace(/%2F/g, '/')
  return apiFetch<{ ok: boolean }>(`/api/v1/db/purls/${encoded}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function createPurl(purl: string, repository_url: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>('/api/v1/db/purls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purl, repository_url }),
  })
}

export function deletePurls(purls: string[]): Promise<DeleteResponse> {
  return apiFetch<DeleteResponse>('/api/v1/db/purls', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purls }),
  })
}

export function importCsv(file: File, strategy: 'upsert' | 'skip_existing'): Promise<ImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('strategy', strategy)
  return apiFetch<ImportResponse>('/api/v1/db/import', {
    method: 'POST',
    body: formData,
  })
}

export function listResolvers(): Promise<string[]> {
  return apiFetch<string[]>('/api/v1/db/resolvers')
}

export function exportSelectedCsv(purls: string[]): Promise<Blob> {
  return apiFetch<Blob>('/api/v1/db/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purls }),
  }, 'blob')
}
