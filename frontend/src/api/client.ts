export class ApiError extends Error {
  status: number
  error: string
  constructor(status: number, error: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.error = error
  }
}

type ResponseFormat = 'json' | 'blob'

export async function apiFetch<T>(
  url: string,
  options?: RequestInit,
  format: ResponseFormat = 'json',
): Promise<T> {
  const res = await fetch(url, options)
  if (!res.ok) {
    let errorData: { error?: string; message?: string } = {}
    try { errorData = await res.json() } catch { /* ignore */ }
    throw new ApiError(
      res.status,
      errorData.error || 'unknown_error',
      errorData.message || `HTTP ${res.status}`,
    )
  }
  return (format === 'blob' ? res.blob() : res.json()) as Promise<T>
}
