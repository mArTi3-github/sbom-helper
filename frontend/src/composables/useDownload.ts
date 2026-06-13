export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const DANGEROUS_PROTOCOLS = /^(javascript|data|vbscript):/i

export function safeUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  if (DANGEROUS_PROTOCOLS.test(url)) return '#'
  return url
}