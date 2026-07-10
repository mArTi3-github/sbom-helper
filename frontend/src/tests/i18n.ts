import { createI18n } from 'vue-i18n'
import { mount, type MountingOptions } from '@vue/test-utils'

const en: Record<string, unknown> = {
  common: { appTitle: 'sbom-helper', pageNotFound: 'Page not found', goHome: 'Go to PURL Resolver', poweredBy: 'Powered by sbom-helper' },
  nav: { purlResolver: 'PURL Resolver', sbomUpdater: 'SBOM Updater', dbAdmin: 'Database Admin', settings: 'Settings', imagesListConverter: 'Images List Converter' },
  purlResolver: { title: 'PURL Resolver', subtitle: 'Resolve a Package URL to its source code repository', placeholder: 'pkg:pypi/requests@2.31.0', resolve: 'Resolve', resolving: 'Resolving...', noRepoUrl: 'No repository URL found', hideDetails: 'Hide details', showDetails: 'Show details', repoUrl: 'Repository URL', repoType: 'Repository Type', repoKind: 'Repository Kind', evidence: 'Evidence', warnings: 'Warnings', versionRef: 'Version Reference', foundBy: 'Found by', resolver: 'Resolver', unknown: 'unknown' },
  settings: { title: 'Settings', subtitle: 'Application settings', savedToast: 'Settings saved', saveFailedToast: 'Failed to save: {message}', language: 'Language', languageEn: 'English', languageRu: 'Russian', tokenCleared: 'Token cleared', cacheCleared: 'Validation cache cleared', tokenCheckComplete: 'Token check complete', errorMessages: { loadFailed: 'Failed to load settings', tokenClearFailed: 'Failed to clear token', tokenCheckFailed: 'Failed to check token', keyClearFailed: 'Failed to clear key', cacheClearFailed: 'Failed to clear validation cache' }, clearToken: 'Clear token', clearKey: 'Clear key', checkValidity: 'Check validity', set: 'set', notSet: 'not set', valid: 'valid', invalid: 'invalid' },
  sbomUpdater: { title: 'SBOM Updater', subtitle: 'Upload a CycloneDX SBOM (JSON) to enrich components with source code repository references', addRow: 'Add row', saved: 'Saved', save: 'Save', process: 'Process', processing: 'Processing SBOM...', downloadEnriched: 'Download enriched SBOM', removeUnresolved: 'Remove unresolved components without subcomponents', ignorePatterns: 'Ignore components matching these criteria:', fieldPlaceholder: 'Field', contains: 'contains', valuePlaceholder: 'Value' },
  imagesListConverter: { title: 'Images List Converter', subtitle: 'Upload a CycloneDX SBOM (JSON) to generate a machine-readable list of container images', convert: 'Convert', processing: 'Processing SBOM...', wasTransformed: 'Transformation applied — the source SBOM was converted to a container image list.', noTransformation: 'No transformation needed — the uploaded file is already a valid image list.', downloadList: 'Download image list' },
  dbAdmin: { title: 'Database Admin', subtitle: 'View, edit, filter, import, and export the resolved_purls table', importTitle: 'Import CSV', loading: 'Loading...', noRecords: 'No records found', edit: 'Edit', del: 'Del', any: 'Any', exportCsv: 'Export CSV', importCsv: 'Import CSV', deleteSelected: 'Delete Selected', apply: 'Apply', reset: 'Reset', total: 'Total:', rows: 'rows', perPage: 'Per page', first: 'First', prev: 'Prev', next: 'Next', last: 'Last', purl: 'PURL', repositoryUrl: 'Repository URL', resolver: 'Resolver', type: 'Type', kind: 'Kind', confidence: 'Confidence', versionRef: 'Version Ref', evidence: 'Evidence', warnings: 'Warnings', resolvedAt: 'Resolved At', actions: 'Actions', csvRef: 'CSV Format Reference', csvRequired: 'Required columns:', csvOptional: 'Optional columns:', csvExample: 'Example:', importOverwrite: 'Overwrite existing', importSkip: 'Skip existing', uploading: 'Uploading...', upload: 'Upload', importing: 'Importing...', imported: 'Imported:', skipped: 'Skipped:', errors: 'Errors:' },
  status: { found: 'Found', not_found: 'Not found', removed: 'Removed', ignored: 'Ignored', skipped: 'Skipped' },
  errors: { file_too_large: 'File size exceeds maximum of {max_size_mb} MB', invalid_json: 'Invalid JSON format', invalid_sbom: 'Invalid SBOM file', network_unavailable: 'Network unavailable', invalid_token: 'GitHub token is invalid or expired', token_not_set: 'GitHub token is not set', invalid_update: 'Invalid update request', purl_not_found: 'PURL not found', invalid_csv: 'Invalid CSV file', invalid_purl: 'Invalid PURL', upstream_error: 'Upstream resolution error', network_error: 'Network error: could not reach the server.', unexpected_error: 'An unexpected error occurred.', unknown_error: 'An unknown error occurred' },
  fileUpload: { labelStrong: 'Choose a file', labelOr: 'or drag it here', hintCsv: 'CSV, up to {sizeMb} MB', hintJson: 'CycloneDX JSON, up to {sizeMb} MB', hintDefault: 'up to {sizeMb} MB', file: 'File:', fileTooLarge: 'File exceeds maximum size of {maxSize} MB.' },
}

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
})

export function mountWithI18n<T>(
  component: T,
  options?: MountingOptions<T>,
) {
  return mount(component as any, {
    ...options,
    global: {
      ...options?.global,
      plugins: [...(options?.global?.plugins ?? []), i18n],
    },
  })
}
