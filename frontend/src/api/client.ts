export class ApiError extends Error {
  constructor(
    public status: number,
    public error: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(url, options)

  if (!res.ok) {
    let errorData: { error?: string; message?: string } = {}
    try {
      errorData = await res.json()
    } catch {
      // ignore parse errors
    }
    throw new ApiError(
      res.status,
      errorData.error || 'unknown_error',
      errorData.message || `HTTP ${res.status}`,
    )
  }

  return res.json() as Promise<T>
}