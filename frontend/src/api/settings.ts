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
