export interface ResolveRequest {
  purl: string
}

export interface ResolveResponse {
  purl: string
  repository_url: string | null
  repository_type: string | null
  repository_kind: string | null
  confidence: string | null
  evidence: string[]
  warnings: string[]
  version_reference: string | null
  resolver: string
  found_by: string
  resolved_at: string
}

export interface ErrorResponse {
  error: string
  message: string
}

export interface SettingsTokenSet {
  github_token: boolean
  librariesio_api_key: boolean
  ecosystems_api_key: boolean
}

export interface SettingsResponse {
  validate_db_urls: boolean
  url_validation_timeout: number
  revalidation_cooldown_hours: number
  retry_max_attempts: number
  retry_base_cooldown_seconds: number
  log_level: string
  librariesio_enabled: boolean
  ecosystems_enabled: boolean
  ecosystems_max_requests_per_second: number
  token_set: SettingsTokenSet
}

export interface SettingsUpdate {
  validate_db_urls?: boolean
  url_validation_timeout?: number
  github_token?: string | null
  librariesio_enabled?: boolean
  librariesio_api_key?: string | null
  ecosystems_enabled?: boolean
  ecosystems_api_key?: string | null
  ecosystems_max_requests_per_second?: number
  revalidation_cooldown_hours?: number
  retry_max_attempts?: number
  retry_base_cooldown_seconds?: number
  log_level?: string
}

export interface ImageItem {
  name: string | null
  version: string | null
  missing_components: boolean
  missing_name: boolean
  missing_version: boolean
  missing_properties: boolean
}

export interface ImagesListResponse {
  was_transformed: boolean
  images: ImageItem[]
  images_list: unknown
}