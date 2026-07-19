export interface ResolveRequest {
  purl: string
}

export interface ResolveResponse {
  purl: string
  repository_url: string | null
  warnings: string[]
  resolver: string
  found_by: string
  resolved_at: string
}

export interface ErrorResponse {
  error: string
  detail?: string
}

export interface SettingsTokenSet {
  librariesio_api_key: boolean
  ecosystems_api_key: boolean
}

export interface SettingsResponse {
  validate_db_urls: boolean
  validate_sbom_refs: boolean
  sbom_multiple_vcs_behavior: string
  url_validation_timeout: number
  revalidation_cooldown_hours: number
  retry_max_attempts: number
  retry_base_cooldown_seconds: number
  log_level: string
  librariesio_enabled: boolean
  ecosystems_enabled: boolean
  ecosystems_max_requests_per_second: number
  batch_semaphore_limit: number
  job_ttl_hours: number
  connectivity_url: string
  connectivity_timeout: number
  json_indent: number
  token_set: SettingsTokenSet
}

export interface SettingsUpdate {
  validate_db_urls?: boolean
  validate_sbom_refs?: boolean
  sbom_multiple_vcs_behavior?: string
  url_validation_timeout?: number
  librariesio_enabled?: boolean
  librariesio_api_key?: string | null
  ecosystems_enabled?: boolean
  ecosystems_api_key?: string | null
  ecosystems_max_requests_per_second?: number
  revalidation_cooldown_hours?: number
  retry_max_attempts?: number
  retry_base_cooldown_seconds?: number
  log_level?: string
  batch_semaphore_limit?: number
  job_ttl_hours?: number
  connectivity_url?: string
  connectivity_timeout?: number
  json_indent?: number
}

export interface ImageItem {
  name: string | null
  version: string | null
  missing_components: boolean
  missing_name: boolean
  missing_version: boolean
  missing_properties: boolean
  duplicates_removed: number
}

export interface ImagesListResponse {
  was_transformed: boolean
  images: ImageItem[]
  images_list: unknown
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface JobRecord {
  job_id: string
  type: string
  status: JobStatus
  progress_current: number
  progress_total: number
  input_filename: string | null
  summary: SbomSummary | null
  results: SbomResultItem[] | null
  error_message: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface JobListResponse {
  jobs: JobRecord[]
}

export interface JobCreateResponse {
  job_id: string
  status: JobStatus
}

export interface IgnorePatternItem {
  field: string
  pattern: string
}

export interface SbomSummary {
  total_purls: number
  found: number
  not_found: number
  skipped: number
  removed: number
  ignored: number
}

export interface SbomResultItem {
  purl: string
  status: 'found' | 'not_found' | 'removed' | 'ignored'
  repository_url: string | null
  found_by?: string
  resolver?: string
  name?: string
  version?: string
}

export interface SbomResponse {
  summary: SbomSummary
  results: SbomResultItem[]
  enriched_sbom: unknown
}

export interface PurlListResponse {
  rows: ResolveResponse[]
  total: number
  page: number
  page_size: number
}

export interface PurlUpdateRequest {
  purl?: string | null
  repository_url?: string | null
}

export interface PurlDeleteRequest {
  purls: string[]
}

export interface DeleteResponse {
  deleted: number
}

export interface ImportErrorItem {
  row: number
  error: string
}

export interface ImportResponse {
  imported: number
  skipped: number
  errors: ImportErrorItem[]
}
