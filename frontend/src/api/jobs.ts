import { apiFetch } from './client'
import type { JobRecord, JobCreateResponse, JobListResponse, IgnorePatternItem } from '../types/api'

export function createSbomEnrichJob(
  file: File,
  removeUnresolved: boolean,
  ignorePatterns: IgnorePatternItem[],
): Promise<JobCreateResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (removeUnresolved) formData.append('remove_unresolved_no_subcomponents', 'true')
  if (ignorePatterns.length > 0) formData.append('ignore_patterns', JSON.stringify(ignorePatterns))
  return apiFetch<JobCreateResponse>('/api/v1/jobs/sbom-enrich', {
    method: 'POST',
    body: formData,
  })
}

export function getJob(jobId: string): Promise<JobRecord> {
  return apiFetch<JobRecord>(`/api/v1/jobs/${jobId}`)
}

export function cancelJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return apiFetch(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' })
}

export function deleteJob(jobId: string): Promise<{ job_id: string; deleted: boolean }> {
  return apiFetch(`/api/v1/jobs/${jobId}`, { method: 'DELETE' })
}

export function listJobs(limit = 20, offset = 0): Promise<JobListResponse> {
  return apiFetch<JobListResponse>(`/api/v1/jobs?limit=${limit}&offset=${offset}`)
}

export function downloadJobResultUrl(jobId: string): string {
  return `/api/v1/jobs/${jobId}/result`
}
