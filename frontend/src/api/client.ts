export class ApiError extends Error {
  status: number
  error: string
  data: Record<string, unknown>
  constructor(status: number, error: string, data: Record<string, unknown> = {}) {
    super(error)
    this.name = 'ApiError'
    this.status = status
    this.error = error
    this.data = data
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
    let errorData: Record<string, unknown> = {}
    try { errorData = await res.json() } catch { /* ignore */ }
    throw new ApiError(
      res.status,
      (errorData.error as string) || 'unknown_error',
      errorData,
    )
  }
  return (format === 'blob' ? res.blob() : res.json()) as Promise<T>
}
