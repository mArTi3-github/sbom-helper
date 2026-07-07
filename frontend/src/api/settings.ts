import { apiFetch } from './client'
import type { SettingsResponse, SettingsUpdate } from '../types/api'

export function getSettings(): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/api/v1/settings')
}

export function updateSettings(body: SettingsUpdate): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/api/v1/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function checkGithubToken(): Promise<{ status: 'valid' | 'invalid' }> {
  return apiFetch<{ status: 'valid' | 'invalid' }>('/api/v1/settings/check-github-token', { method: 'POST' })
}

export function clearValidationCache(): Promise<{ status: string }> {
  return apiFetch('/api/v1/settings/clear-validation-cache', { method: 'POST' })
}
