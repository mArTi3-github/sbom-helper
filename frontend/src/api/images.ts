import { apiFetch } from './client'
import type { ImagesListResponse } from '../types/api'

export function convertImagesList(file: File): Promise<ImagesListResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<ImagesListResponse>('/api/v1/convert/images-list', {
    method: 'POST',
    body: formData,
  })
}
