import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import SbomFixer from './SbomFixer.vue'
import { ApiError } from '../api/client'
import { useSettingsStore } from '../stores/useSettingsStore'
import { downloadJson } from '../composables/useDownload'
import type { SbomFixOptions, SbomFixResponse, SettingsResponse } from '../types/api'

const defaultOptions: SbomFixOptions = {
  root: {
    reorder: true,
    set_spec_version: true,
    spec_version: '1.7',
    remove_dependencies: true,
    remove_services: true,
    increment_version: true,
  },
  metadata: {
    add_timestamp: true,
    reorder: true,
    remove_properties: true,
    remove_tools: true,
    component: {
      reorder: true,
      remove_external_references: true,
      remove_properties: true,
      remove_purl: false,
      remove_scope: true,
      rename_supplier: true,
    },
  },
  components: {
    reorder: true,
    remove_hashes: true,
    remove_scope: true,
    filter_external_references: true,
    filter_properties: true,
    fill_missing_gost_properties: false,
  },
}

const settingsResponse: SettingsResponse = {
  validate_db_urls: false,
  validate_sbom_refs: false,
  sbom_multiple_vcs_behavior: 'keep-first',
  url_validation_timeout: 5,
  revalidation_cooldown_hours: 24,
  retry_max_attempts: 3,
  retry_base_cooldown_seconds: 5,
  log_level: 'INFO',
  librariesio_enabled: false,
  depsdev_enabled: true,
  apk_resolver_enabled: false,
  ecosystems_enabled: false,
  ecosystems_max_requests_per_second: 2,
  batch_semaphore_limit: 10,
  batch_max_items: 100,
  connectivity_url: 'https://github.com',
  connectivity_timeout: 2,
  json_indent: 2,
  job_ttl_hours: 24,
  llm_resolver_enabled: false,
  llm_resolver_base_url: null,
  llm_resolver_model: null,
  llm_resolver_attempts_count: 2,
  llm_resolver_timeout: 60,
  token_set: { librariesio_api_key: false, ecosystems_api_key: false, llm_resolver_api_key: false },
}

const changedResponse: SbomFixResponse = {
  changed: true,
  fixed_sbom: { bomFormat: 'CycloneDX' },
  stats: [{ rule_id: 'root.reorder', count: 1 }],
  issues: [],
}

const unchangedResponse: SbomFixResponse = {
  changed: false,
  fixed_sbom: { bomFormat: 'CycloneDX' },
  stats: [],
  issues: [],
}

const statsResponse: SbomFixResponse = {
  changed: true,
  fixed_sbom: { bomFormat: 'CycloneDX' },
  stats: [
    { rule_id: 'root.reorder', count: 2 },
    { rule_id: 'components.remove_hashes', count: 0 },
  ],
  issues: [],
}

const issuesResponse: SbomFixResponse = {
  changed: true,
  fixed_sbom: { bomFormat: 'CycloneDX' },
  stats: [{ rule_id: 'root.reorder', count: 2 }],
  issues: [
    {
      code: 'component.missing_gost_properties',
      path: '$.components[0]',
      component: 'openssl',
      details: { missing: ['GOST:attack_surface', 'GOST:security_function'] },
    },
    {
      code: 'root.spec_version_not_allowed',
      path: '$',
      component: null,
      details: { expected: '1.6 or 1.7' },
    },
  ],
}

const getFixOptionsMock = vi.fn()
const saveFixOptionsMock = vi.fn()
const fixSbomMock = vi.fn()
const getSettingsMock = vi.fn()
const updateSettingsMock = vi.fn()

vi.mock('../api/sbom', () => ({
  getFixOptions: () => getFixOptionsMock(),
  saveFixOptions: (options: SbomFixOptions) => saveFixOptionsMock(options),
  fixSbom: (file: File, options: SbomFixOptions) => fixSbomMock(file, options),
}))

vi.mock('../api/settings', () => ({
  getSettings: () => getSettingsMock(),
  updateSettings: (body: unknown) => updateSettingsMock(body),
}))

vi.mock('../composables/useDownload', () => ({
  downloadJson: vi.fn(),
}))

function cloneOptions(): SbomFixOptions {
  return JSON.parse(JSON.stringify(defaultOptions)) as SbomFixOptions
}

async function mountFixer() {
  const wrapper = mountWithI18n(SbomFixer)
  await flushPromises()
  return wrapper
}

function rule(ruleId: string) {
  return `[data-rule="${ruleId}"]`
}

function masterFor(wrapper: Awaited<ReturnType<typeof mountFixer>>, group: string) {
  return wrapper.find(`[data-group="${group}"] .master-checkbox`)
}

async function selectFile(
  wrapper: Awaited<ReturnType<typeof mountFixer>>,
  name = 'sbom.json',
) {
  const file = new File(['{}'], name, { type: 'application/json' })
  await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
  await flushPromises()
  return file
}

describe('SbomFixer.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getFixOptionsMock.mockResolvedValue({ options: cloneOptions() })
    saveFixOptionsMock.mockResolvedValue({ status: 'saved' })
    fixSbomMock.mockResolvedValue(changedResponse)
    getSettingsMock.mockResolvedValue(settingsResponse)
    updateSettingsMock.mockResolvedValue(settingsResponse)
  })

  it('renders the warning banner about almost all fixes being enabled', async () => {
    const wrapper = await mountFixer()
    const banner = wrapper.find('.warning-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('Almost all fixes are enabled by default')
  })

  it('loads options and settings on mount and fills the form', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        root: { ...cloneOptions().root, spec_version: '1.6', increment_version: false },
      },
    })
    const wrapper = await mountFixer()

    expect(getFixOptionsMock).toHaveBeenCalledTimes(1)
    expect(getSettingsMock).toHaveBeenCalledTimes(1)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).value).toBe('1.6')
    expect((wrapper.find(rule('root.increment_version')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('root.reorder')).element as HTMLInputElement).checked).toBe(true)
  })

  it('falls back to defaults with a warning when options fail to load', async () => {
    getFixOptionsMock.mockRejectedValueOnce(new ApiError(500, 'unknown_error'))
    const wrapper = await mountFixer()

    expect(wrapper.find('.options-warning').exists()).toBe(true)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).value).toBe('1.7')
    expect((wrapper.find(rule('root.reorder')).element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.find('.fix-button').exists()).toBe(true)
  })

  it('does not block the page when settings fail to load', async () => {
    getSettingsMock.mockRejectedValueOnce(new Error('settings down'))
    const wrapper = await mountFixer()

    expect(wrapper.find('.warning-banner').exists()).toBe(true)
    expect(useSettingsStore().jsonIndent).toBe(4)
  })

  it('root master toggles every root option', async () => {
    const wrapper = await mountFixer()
    const master = masterFor(wrapper, 'root')

    await master.setValue(false)
    for (const id of [
      'root.reorder',
      'root.set_spec_version',
      'root.remove_dependencies',
      'root.remove_services',
      'root.increment_version',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked).toBe(false)
    }

    await master.setValue(true)
    for (const id of [
      'root.reorder',
      'root.set_spec_version',
      'root.remove_dependencies',
      'root.remove_services',
      'root.increment_version',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked).toBe(true)
    }
  })

  it('metadata master also toggles metadata.component options', async () => {
    const wrapper = await mountFixer()
    const master = masterFor(wrapper, 'metadata')

    await master.setValue(true)
    for (const id of [
      'metadata.add_timestamp',
      'metadata.reorder',
      'metadata.remove_properties',
      'metadata.remove_tools',
      'metadata_component.reorder',
      'metadata_component.remove_external_references',
      'metadata_component.remove_properties',
      'metadata_component.remove_purl',
      'metadata_component.remove_scope',
      'metadata_component.rename_supplier',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(true)
    }

    await master.setValue(false)
    for (const id of [
      'metadata.add_timestamp',
      'metadata.reorder',
      'metadata.remove_properties',
      'metadata.remove_tools',
      'metadata_component.reorder',
      'metadata_component.remove_external_references',
      'metadata_component.remove_properties',
      'metadata_component.remove_purl',
      'metadata_component.remove_scope',
      'metadata_component.rename_supplier',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
  })

  it('metadata-component master does not change metadata options', async () => {
    const wrapper = await mountFixer()
    const subMaster = masterFor(wrapper, 'metadata-component')

    await subMaster.setValue(true)
    await subMaster.setValue(false)

    expect((wrapper.find(rule('metadata.reorder')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find(rule('metadata.add_timestamp')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find(rule('metadata.remove_properties')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find(rule('metadata.remove_tools')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find(rule('metadata_component.reorder')).element as HTMLInputElement).checked).toBe(false)
  })

  it('marks partially selected masters as indeterminate', async () => {
    const wrapper = await mountFixer()

    expect((masterFor(wrapper, 'root').element as HTMLInputElement).indeterminate).toBe(false)
    expect((masterFor(wrapper, 'metadata').element as HTMLInputElement).indeterminate).toBe(true)
    expect((masterFor(wrapper, 'components').element as HTMLInputElement).indeterminate).toBe(true)

    await wrapper.find(rule('metadata_component.remove_purl')).setValue(true)
    expect((masterFor(wrapper, 'metadata').element as HTMLInputElement).indeterminate).toBe(false)
    expect((masterFor(wrapper, 'metadata').element as HTMLInputElement).checked).toBe(true)
  })

  it('select all and clear all operate within their own group', async () => {
    const wrapper = await mountFixer()

    await wrapper.find('.group-card[data-group="root"] .clear-all').trigger('click')
    expect((wrapper.find(rule('root.reorder')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('components.reorder')).element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('.group-card[data-group="root"] .select-all').trigger('click')
    expect((wrapper.find(rule('root.reorder')).element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('[data-group="metadata-component"] .clear-all').trigger('click')
    expect((wrapper.find(rule('metadata_component.remove_purl')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('metadata.reorder')).element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('[data-group="metadata-component"] .select-all').trigger('click')
    expect((wrapper.find(rule('metadata_component.remove_purl')).element as HTMLInputElement).checked).toBe(true)
  })

  it('restores defaults without saving them', async () => {
    const wrapper = await mountFixer()

    await wrapper.find('.group-card[data-group="root"] .clear-all').trigger('click')
    await wrapper.find('.spec-version-input').setValue('1.6')
    await wrapper.find('.reset-defaults').trigger('click')

    expect((wrapper.find(rule('root.reorder')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find(rule('components.fill_missing_gost_properties')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('metadata_component.remove_purl')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).value).toBe('1.7')
    expect(saveFixOptionsMock).not.toHaveBeenCalled()
  })

  it('saves the current options and shows Saved', async () => {
    const wrapper = await mountFixer()

    await wrapper.find(rule('components.fill_missing_gost_properties')).setValue(true)
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()

    expect(saveFixOptionsMock).toHaveBeenCalledTimes(1)
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved).toEqual({
      ...cloneOptions(),
      components: { ...cloneOptions().components, fill_missing_gost_properties: true },
    })
    expect(wrapper.find('.save-status').text()).toContain('Saved')
  })

  it('clears the Saved status when options change or a new file is selected', async () => {
    const wrapper = await mountFixer()

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).toContain('Saved')

    await wrapper.find(rule('root.reorder')).setValue(false)
    await flushPromises()
    expect(wrapper.find('.save-status').text()).not.toContain('Saved')

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).toContain('Saved')

    await selectFile(wrapper)
    expect(wrapper.find('.save-status').text()).not.toContain('Saved')
  })

  it('shows a save failure in save-status, not in the error block', async () => {
    saveFixOptionsMock.mockRejectedValueOnce(new ApiError(500, 'options_save_failed'))
    const wrapper = await mountFixer()

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()

    expect(wrapper.find('.save-status').text()).toContain('Could not save fix options')
    expect(wrapper.find('.save-status').classes()).toContain('save-status-error')
    expect(wrapper.find('.error-msg').exists()).toBe(false)
  })

  it('shows a network save failure in save-status', async () => {
    saveFixOptionsMock.mockRejectedValueOnce(new Error('offline'))
    const wrapper = await mountFixer()

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()

    expect(wrapper.find('.save-status').text()).toContain('Network error')
    expect(wrapper.find('.error-msg').exists()).toBe(false)
  })

  it('disables the spec version input when set_spec_version is off', async () => {
    const wrapper = await mountFixer()

    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).disabled).toBe(false)
    await wrapper.find(rule('root.set_spec_version')).setValue(false)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).disabled).toBe(true)
  })

  it('disables the fix button until a file is selected', async () => {
    const wrapper = await mountFixer()

    expect((wrapper.find('.fix-button').element as HTMLButtonElement).disabled).toBe(true)
    await selectFile(wrapper)
    expect((wrapper.find('.fix-button').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('shows loading, sends file and options, then renders the changed status', async () => {
    let resolveFix: (value: SbomFixResponse) => void = () => {}
    const pending = new Promise<SbomFixResponse>((resolve) => {
      resolveFix = resolve
    })
    fixSbomMock.mockReturnValueOnce(pending)
    const wrapper = await mountFixer()
    const file = await selectFile(wrapper)

    await wrapper.find('.fix-button').trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.loading').exists()).toBe(true)

    resolveFix(changedResponse)
    await flushPromises()

    expect(fixSbomMock).toHaveBeenCalledTimes(1)
    expect(fixSbomMock).toHaveBeenCalledWith(file, cloneOptions())
    expect(wrapper.find('.loading').exists()).toBe(false)
    const card = wrapper.find('.status-card')
    expect(card.classes()).toContain('status-changed')
    expect(card.text()).toContain('Changes applied')
  })

  it('renders the unchanged status when changed is false', async () => {
    fixSbomMock.mockResolvedValueOnce(unchangedResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)

    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const card = wrapper.find('.status-card')
    expect(card.classes()).toContain('status-unchanged')
    expect(card.text()).toContain('No changes needed')
  })

  it('shows invalid_options as an error message', async () => {
    fixSbomMock.mockRejectedValueOnce(new ApiError(400, 'invalid_options'))
    const wrapper = await mountFixer()
    await selectFile(wrapper)

    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-msg').text()).toContain('Invalid fix options')
    expect(wrapper.find('.status-card').exists()).toBe(false)
  })

  it('shows invalid_sbom as an error message', async () => {
    fixSbomMock.mockRejectedValueOnce(new ApiError(400, 'invalid_sbom'))
    const wrapper = await mountFixer()
    await selectFile(wrapper)

    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-msg').text()).toContain('Invalid SBOM file')
  })

  it('shows a network error message when the request fails', async () => {
    fixSbomMock.mockRejectedValueOnce(new Error('offline'))
    const wrapper = await mountFixer()
    await selectFile(wrapper)

    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })

  it('resets the result but keeps options when a new file is selected', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.status-card').exists()).toBe(true)

    await wrapper.find(rule('root.reorder')).setValue(false)
    await selectFile(wrapper, 'other.json')

    expect(wrapper.find('.status-card').exists()).toBe(false)
    expect((wrapper.find(rule('root.reorder')).element as HTMLInputElement).checked).toBe(false)
  })

  it('clears an error when a new file is selected', async () => {
    fixSbomMock.mockRejectedValueOnce(new ApiError(400, 'invalid_sbom'))
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)

    await selectFile(wrapper, 'other.json')

    expect(wrapper.find('.error-msg').exists()).toBe(false)
  })

  it('renders change statistics in an open spoiler, including zero counts', async () => {
    fixSbomMock.mockResolvedValueOnce(statsResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const spoiler = wrapper.find('.stats-spoiler')
    expect(spoiler.exists()).toBe(true)
    expect((spoiler.element as HTMLDetailsElement).open).toBe(true)

    expect(wrapper.find('.stats-table').text()).toContain('Rule')
    expect(wrapper.find('.stats-table').text()).toContain('Changes')
    const rows = wrapper.findAll('.stats-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Reorder root fields')
    expect(rows[0].text()).toContain('2')
    expect(rows[1].text()).toContain('Remove hashes')
    expect(rows[1].text()).toContain('0')
  })

  it('renders issues in a closed spoiler and builds the table only when opened', async () => {
    fixSbomMock.mockResolvedValueOnce(issuesResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const spoiler = wrapper.find('.issues-spoiler')
    expect(spoiler.exists()).toBe(true)
    expect((spoiler.element as HTMLDetailsElement).open).toBe(false)
    expect(spoiler.text()).toContain('Show non-conformities (2)')
    expect(wrapper.find('.issues-table').exists()).toBe(false)

    ;(spoiler.element as HTMLDetailsElement).open = true
    await spoiler.trigger('toggle')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.issues-table').exists()).toBe(true)
    const headers = wrapper.find('.issues-table thead').text()
    expect(headers).toContain('Code')
    expect(headers).toContain('Path')
    expect(headers).toContain('Component')
    expect(headers).toContain('Details')

    const rows = wrapper.findAll('.issues-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Missing GOST properties')
    expect(rows[0].text()).toContain('$.components[0]')
    expect(rows[0].text()).toContain('openssl')
    expect(rows[0].text()).toContain('GOST:attack_surface, GOST:security_function')
    expect(rows[0].findAll('td')[0].text()).toContain('GOST:attack_surface, GOST:security_function')
    expect(rows[0].findAll('td')[0].attributes('title')).toBeTruthy()
    expect(rows[1].text()).toContain('specVersion')
    expect(rows[1].text()).toContain('{"expected":"1.6 or 1.7"}')
  })

  it('falls back to the bare issue code when no translation exists', async () => {
    fixSbomMock.mockResolvedValueOnce({
      ...issuesResponse,
      issues: [
        {
          code: 'custom.unknown_issue',
          path: '$',
          component: null,
          details: { reason: 'test' },
        },
      ],
    })
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const spoiler = wrapper.find('.issues-spoiler')
    ;(spoiler.element as HTMLDetailsElement).open = true
    await spoiler.trigger('toggle')
    await wrapper.vm.$nextTick()

    const cell = wrapper.find('.issues-table tbody tr td')
    expect(cell.text()).toBe('custom.unknown_issue')
    expect(cell.text()).not.toContain('sbomFixer.issues')
  })

  it('shows a green card and no spoiler when no issues remain', async () => {
    fixSbomMock.mockResolvedValueOnce(unchangedResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const card = wrapper.find('.no-issues-card')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('No non-conformities remaining')
    expect(wrapper.find('.issues-spoiler').exists()).toBe(false)
  })

  it('downloads the fixed sbom using the configured indent', async () => {
    fixSbomMock.mockResolvedValueOnce(statsResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    await wrapper.find('.download-button').trigger('click')

    expect(downloadJson).toHaveBeenCalledWith(statsResponse.fixed_sbom, 'sbom_fixed.json', 2)
  })

  it('falls back to indent 4 for downloads when settings fail to load', async () => {
    getSettingsMock.mockRejectedValueOnce(new Error('settings down'))
    fixSbomMock.mockResolvedValueOnce(statsResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper, 'my-sbom.json')
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    await wrapper.find('.download-button').trigger('click')

    expect(downloadJson).toHaveBeenCalledWith(statsResponse.fixed_sbom, 'my-sbom_fixed.json', 4)
  })

  it('uses indent 4 on settings failure even when the store holds a stale value', async () => {
    useSettingsStore().jsonIndent = 2
    getSettingsMock.mockRejectedValueOnce(new Error('settings down'))
    fixSbomMock.mockResolvedValueOnce(statsResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper, 'stale.json')
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    await wrapper.find('.download-button').trigger('click')

    expect(downloadJson).toHaveBeenCalledWith(statsResponse.fixed_sbom, 'stale_fixed.json', 4)
  })

  it('collapses and reopens the statistics spoiler', async () => {
    fixSbomMock.mockResolvedValueOnce(statsResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    let spoiler = wrapper.find('.stats-spoiler')
    ;(spoiler.element as HTMLDetailsElement).open = false
    await spoiler.trigger('toggle')
    await wrapper.vm.$nextTick()
    spoiler = wrapper.find('.stats-spoiler')
    expect((spoiler.element as HTMLDetailsElement).open).toBe(false)

    ;(spoiler.element as HTMLDetailsElement).open = true
    await spoiler.trigger('toggle')
    await wrapper.vm.$nextTick()
    spoiler = wrapper.find('.stats-spoiler')
    expect((spoiler.element as HTMLDetailsElement).open).toBe(true)
  })

  it('resets spoiler state when a new result arrives', async () => {
    fixSbomMock.mockResolvedValue(issuesResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const issuesSpoiler = wrapper.find('.issues-spoiler')
    ;(issuesSpoiler.element as HTMLDetailsElement).open = true
    await issuesSpoiler.trigger('toggle')
    const statsSpoiler = wrapper.find('.stats-spoiler')
    ;(statsSpoiler.element as HTMLDetailsElement).open = false
    await statsSpoiler.trigger('toggle')
    await wrapper.vm.$nextTick()

    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    expect((wrapper.find('.issues-spoiler').element as HTMLDetailsElement).open).toBe(false)
    expect((wrapper.find('.stats-spoiler').element as HTMLDetailsElement).open).toBe(true)
  })
})
