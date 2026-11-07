import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountWithI18n } from '../tests/i18n'
import SbomFixer from './SbomFixer.vue'
import { ALL_FIX_RULES, COMPONENTS_RULES, LICENSES_RULES } from './sbomFixerRules'
import { ApiError } from '../api/client'
import { useSettingsStore } from '../stores/useSettingsStore'
import { downloadJson } from '../composables/useDownload'
import type { SbomFixOptions, SbomFixResponse, SettingsResponse } from '../types/api'

const defaultOptions: SbomFixOptions = {
  reorder: true,
  set_spec_version: true,
  spec_version: '1.7',
  increment_version: true,
  add_timestamp: true,
  add_manufacturer: true,
  manufacturer: 'Positive Technologies',
  components: {
    remove_leaf_missing_purl: false,
    remove_leaf_invalid_purl: false,
    remove_leaf_missing_version: false,
    lowercase_purl: true,
    purl_case_mode: 'sbom_checker',
    filter_external_references: true,
    filter_properties: true,
    fill_missing_gost_properties: false,
    add_provided_by: true,
    provided_by_patterns: [
      {
        field: 'purl',
        pattern: 'pkg:deb/astra',
        provided_by:
          'Операционная система специального назначения "Astra Linux Special Edition"',
      },
    ],
  },
  licenses: {
    filter_non_proprietary: false,
    add_proprietary: false,
    remove_proprietary_source_references: false,
    add_patterns: [],
  },
  optional_fields: {
    keep: [
      'metadata.tools',
      'metadata.component.properties',
      'metadata.component.group',
      'metadata.component.purl',
      'metadata.component.externalReferences',
      'metadata.component.bom-ref',
      'components[].group',
      'components[].licenses',
      'components[].description',
      'components[].bom-ref',
    ],
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
  stats: [{ rule_id: 'reorder', count: 1 }],
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
    { rule_id: 'reorder', count: 2 },
    { rule_id: 'components.filter_properties', count: 0 },
  ],
  issues: [],
}

const statsWithFieldResponse: SbomFixResponse = {
  changed: true,
  fixed_sbom: { bomFormat: 'CycloneDX' },
  stats: [{ rule_id: 'optional_fields.remove', field: 'components[].scope', count: 3 }],
  issues: [],
}

const issuesResponse: SbomFixResponse = {
  changed: true,
  fixed_sbom: { bomFormat: 'CycloneDX' },
  stats: [{ rule_id: 'reorder', count: 2 }],
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

const fieldCatalogResponse = {
  fstec_fields: [
    { path: 'root.bomFormat', status: 'mandatory' },
    { path: 'root.serialNumber', status: 'optional' },
  ],
  default_keep: [...defaultOptions.optional_fields.keep],
}

const getFixOptionsMock = vi.fn()
const saveFixOptionsMock = vi.fn()
const fixSbomMock = vi.fn()
const analyzeSbomMock = vi.fn()
const getFieldCatalogMock = vi.fn()
const getSettingsMock = vi.fn()
const updateSettingsMock = vi.fn()

vi.mock('../api/sbom', () => ({
  getFixOptions: () => getFixOptionsMock(),
  saveFixOptions: (options: SbomFixOptions) => saveFixOptionsMock(options),
  fixSbom: (file: File, options: SbomFixOptions, removeFields: string[]) =>
    fixSbomMock(file, options, removeFields),
  analyzeSbom: (file: File) => analyzeSbomMock(file),
  getFieldCatalog: () => getFieldCatalogMock(),
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
    analyzeSbomMock.mockResolvedValue({ fields: [] })
    getFieldCatalogMock.mockResolvedValue(fieldCatalogResponse)
    getSettingsMock.mockResolvedValue(settingsResponse)
    updateSettingsMock.mockResolvedValue(settingsResponse)
  })

  it('renders help for every rule and no warning banner', async () => {
    const wrapper = await mountFixer()
    expect(wrapper.find('.warning-banner').exists()).toBe(false)
    expect(wrapper.findAll('.rule-help-button')).toHaveLength(ALL_FIX_RULES.length)
    for (const rule of ALL_FIX_RULES) {
      expect(wrapper.find(`[data-help-for="${rule.id}"]`).exists(), rule.id).toBe(true)
    }
  })

  it('opens rule help with description and both examples', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-help-for="components.filter_properties"]').trigger('click')
    const panel = wrapper.find('[data-rule-row="components.filter_properties"] .rule-help-panel')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('GOST')
    expect(panel.findAll('pre')).toHaveLength(2)
  })

  it('closes the same help on a second click and keeps only one panel open', async () => {
    const wrapper = await mountFixer()
    const first = wrapper.find('[data-help-for="reorder"]')
    await first.trigger('click')
    expect(wrapper.findAll('.rule-help-panel')).toHaveLength(1)

    await wrapper.find('[data-help-for="increment_version"]').trigger('click')
    expect(wrapper.findAll('.rule-help-panel')).toHaveLength(1)
    expect(wrapper.find('[data-rule-row="increment_version"] .rule-help-panel').exists()).toBe(true)

    await wrapper.find('[data-help-for="increment_version"]').trigger('click')
    expect(wrapper.findAll('.rule-help-panel')).toHaveLength(0)
  })

  it('closes help on Escape', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-help-for="reorder"]').trigger('click')
    await wrapper.find('[data-rule-row="reorder"] .rule-help').trigger('keydown', { key: 'Escape' })
    expect(wrapper.findAll('.rule-help-panel')).toHaveLength(0)
  })

  it('does not change the checkbox when its help is opened', async () => {
    const wrapper = await mountFixer()
    const checkbox = wrapper.find(rule('components.filter_properties'))
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
    await wrapper.find('[data-help-for="components.filter_properties"]').trigger('click')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  })

  it('does not toggle the spec version rule when the text input is clicked', async () => {
    const wrapper = await mountFixer()
    const checkbox = wrapper.find(rule('set_spec_version'))
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
    await wrapper.find('.spec-version-input').trigger('click')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  })

  it('saves the option bound to the row that was toggled', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('components.fill_missing_gost_properties')).setValue(true)
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(saveFixOptionsMock).toHaveBeenCalledTimes(1)
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.components.fill_missing_gost_properties).toBe(true)
    expect(saved.reorder).toBe(true)
  })

  it('loads options and settings on mount and fills the form', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        spec_version: '1.6',
        increment_version: false,
      },
    })
    const wrapper = await mountFixer()

    expect(getFixOptionsMock).toHaveBeenCalledTimes(1)
    expect(getSettingsMock).toHaveBeenCalledTimes(1)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).value).toBe('1.6')
    expect((wrapper.find(rule('increment_version')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)
  })

  it('falls back to defaults with a warning when options fail to load', async () => {
    getFixOptionsMock.mockRejectedValueOnce(new ApiError(500, 'unknown_error'))
    const wrapper = await mountFixer()

    expect(wrapper.find('.options-warning').exists()).toBe(true)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).value).toBe('1.7')
    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.find('.fix-button').exists()).toBe(true)
  })

  it('does not block the page when settings fail to load', async () => {
    getSettingsMock.mockRejectedValueOnce(new Error('settings down'))
    const wrapper = await mountFixer()

    expect(wrapper.find('.group-card').exists()).toBe(true)
    expect(useSettingsStore().jsonIndent).toBe(4)
  })

  it('basic master toggles every base option', async () => {
    const wrapper = await mountFixer()
    const master = masterFor(wrapper, 'basic')

    await master.setValue(false)
    for (const id of [
      'reorder',
      'set_spec_version',
      'increment_version',
      'add_timestamp',
      'add_manufacturer',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked).toBe(false)
    }

    await master.setValue(true)
    for (const id of [
      'reorder',
      'set_spec_version',
      'increment_version',
      'add_timestamp',
      'add_manufacturer',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked).toBe(true)
    }
  })

  it('marks partially selected masters as indeterminate', async () => {
    const wrapper = await mountFixer()

    expect((masterFor(wrapper, 'basic').element as HTMLInputElement).indeterminate).toBe(false)
    expect((masterFor(wrapper, 'components').element as HTMLInputElement).indeterminate).toBe(true)

    await wrapper.find(rule('add_manufacturer')).setValue(false)
    expect((masterFor(wrapper, 'basic').element as HTMLInputElement).indeterminate).toBe(true)
    expect((masterFor(wrapper, 'basic').element as HTMLInputElement).checked).toBe(false)
  })

  it('select all and clear all operate within their own group', async () => {
    const wrapper = await mountFixer()

    await wrapper.find('.group-card[data-group="basic"] .clear-all').trigger('click')
    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('components.filter_properties')).element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('.group-card[data-group="basic"] .select-all').trigger('click')
    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('.group-card[data-group="components"] .clear-all').trigger('click')
    for (const id of [
      'components.remove_leaf_missing_purl',
      'components.remove_leaf_invalid_purl',
      'components.remove_leaf_missing_version',
      'components.filter_external_references',
      'components.filter_properties',
      'components.fill_missing_gost_properties',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked).toBe(false)
    }
    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('.group-card[data-group="components"] .select-all').trigger('click')
    for (const id of [
      'components.remove_leaf_missing_purl',
      'components.remove_leaf_invalid_purl',
      'components.remove_leaf_missing_version',
      'components.filter_external_references',
      'components.filter_properties',
      'components.fill_missing_gost_properties',
    ]) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked).toBe(true)
    }
  })

  it('renders a component rule row with help for every component rule', async () => {
    const wrapper = await mountFixer()
    const card = wrapper.find('.group-card[data-group="components"]')
    expect(card.findAll('[data-rule-row]')).toHaveLength(COMPONENTS_RULES.length)
    expect(card.findAll('.rule-help-button')).toHaveLength(COMPONENTS_RULES.length)
  })

  it('saves the three leaf removal flags as disabled by default', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.components.remove_leaf_missing_purl).toBe(false)
    expect(saved.components.remove_leaf_invalid_purl).toBe(false)
    expect(saved.components.remove_leaf_missing_version).toBe(false)
  })

  it('resets leaf removal flags to false', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('components.remove_leaf_missing_purl')).setValue(true)
    await wrapper.find(rule('components.remove_leaf_invalid_purl')).setValue(true)
    await wrapper.find(rule('components.remove_leaf_missing_version')).setValue(true)
    await wrapper.find('.reset-defaults').trigger('click')
    expect((wrapper.find(rule('components.remove_leaf_missing_purl')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('components.remove_leaf_invalid_purl')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('components.remove_leaf_missing_version')).element as HTMLInputElement).checked).toBe(false)
  })

  it('defaults the lowercase PURL rule to enabled with sbom_checker mode', async () => {
    const wrapper = await mountFixer()
    expect((wrapper.find(rule('components.lowercase_purl')).element as HTMLInputElement).checked).toBe(true)
    expect(
      (wrapper.find('[data-purl-case-mode-option="sbom_checker"]').element as HTMLInputElement).checked,
    ).toBe(true)
    expect(
      (wrapper.find('[data-purl-case-mode-option="purl_spec"]').element as HTMLInputElement).checked,
    ).toBe(false)
  })

  it('disables the PURL case mode selector while the rule is off', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('components.lowercase_purl')).setValue(false)
    expect(
      (wrapper.find('[data-purl-case-mode-option="sbom_checker"]').element as HTMLInputElement).disabled,
    ).toBe(true)
    expect(
      (wrapper.find('[data-purl-case-mode-option="purl_spec"]').element as HTMLInputElement).disabled,
    ).toBe(true)
  })

  it('saves the selected PURL case mode and sends it with a fix', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-purl-case-mode-option="purl_spec"]').setValue(true)
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.components.purl_case_mode).toBe('purl_spec')

    const file = await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    const sent = fixSbomMock.mock.calls[0][1] as SbomFixOptions
    expect(sent.components.purl_case_mode).toBe('purl_spec')
    expect(fixSbomMock).toHaveBeenCalledWith(file, expect.anything(), [])
  })

  it('resets the PURL case mode to sbom_checker', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-purl-case-mode-option="purl_spec"]').setValue(true)
    await wrapper.find('.reset-defaults').trigger('click')
    expect(
      (wrapper.find('[data-purl-case-mode-option="sbom_checker"]').element as HTMLInputElement).checked,
    ).toBe(true)
  })

  it('describes both PURL case modes in the help panel', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-help-for="components.lowercase_purl"]').trigger('click')
    const panel = wrapper.find('[data-rule-row="components.lowercase_purl"] .rule-help-panel')
    expect(panel.text()).toContain('sbom-checker')
    expect(panel.text()).toContain('purl-spec')
    expect(panel.text().toLowerCase()).toContain('some checker warnings')
  })

  it('renders the licenses card with three rules and help', async () => {
    const wrapper = await mountFixer()
    const card = wrapper.find('.group-card[data-group="licenses"]')
    expect(card.exists()).toBe(true)
    expect(card.findAll('[data-rule-row]')).toHaveLength(3)
    expect(card.findAll('.rule-help-button')).toHaveLength(3)
    for (const rule of LICENSES_RULES) {
      expect(card.find(`[data-help-for="${rule.id}"]`).exists(), rule.id).toBe(true)
    }
  })

  it('toggles all three license rules with the master checkbox', async () => {
    const wrapper = await mountFixer()
    const master = masterFor(wrapper, 'licenses')
    await master.setValue(true)
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(true)
    }
    await master.setValue(false)
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
  })

  it('selects and clears all license rules with the card buttons', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('.group-card[data-group="licenses"] .select-all').trigger('click')
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(true)
    }
    await wrapper.find('.group-card[data-group="licenses"] .clear-all').trigger('click')
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
  })

  it('saves the licenses block loaded from the server', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          filter_non_proprietary: true,
          add_proprietary: false,
          remove_proprietary_source_references: false,
          add_patterns: [{ field: 'name', pattern: 'vendor' }],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.licenses.filter_non_proprietary).toBe(true)
    expect(saved.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })

  it('shows one empty pattern row when no patterns are saved', async () => {
    const wrapper = await mountFixer()
    const rows = wrapper.findAll('[data-group="licenses"] [data-pattern-row]')
    expect(rows).toHaveLength(1)
    expect((rows[0].find('[data-pattern-field]').element as HTMLInputElement).value).toBe('')
    expect((rows[0].find('[data-pattern-value]').element as HTMLInputElement).value).toBe('')
  })

  it('fills pattern rows from the loaded options', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          ...cloneOptions().licenses,
          add_patterns: [{ field: 'name', pattern: 'vendor' }],
        },
      },
    })
    const wrapper = await mountFixer()
    const rows = wrapper.findAll('[data-group="licenses"] [data-pattern-row]')
    expect(rows).toHaveLength(1)
    expect((rows[0].find('[data-pattern-field]').element as HTMLInputElement).value).toBe('name')
    expect((rows[0].find('[data-pattern-value]').element as HTMLInputElement).value).toBe('vendor')
  })

  it('adds and removes pattern rows', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)
    await wrapper.find('[data-action="add-pattern"]').trigger('click')
    expect(wrapper.findAll('[data-group="licenses"] [data-pattern-row]')).toHaveLength(2)
    await wrapper.findAll('[data-action="remove-pattern"]')[1].trigger('click')
    expect(wrapper.findAll('[data-group="licenses"] [data-pattern-row]')).toHaveLength(1)
  })

  it('disables the pattern editor while the add rule is off', async () => {
    const wrapper = await mountFixer()
    expect(wrapper.find('[data-pattern-field]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-pattern-value]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-action="remove-pattern"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-action="add-pattern"]').attributes('disabled')).toBeDefined()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)
    expect(wrapper.find('[data-pattern-field]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-pattern-value]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-action="remove-pattern"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-action="add-pattern"]').attributes('disabled')).toBeUndefined()
  })

  it('keeps pattern row values when the add rule is turned off', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)
    await wrapper.find('[data-pattern-field]').setValue('name')
    await wrapper.find('[data-pattern-value]').setValue('vendor')
    await wrapper.find(rule('licenses.add_proprietary')).setValue(false)
    expect((wrapper.find('[data-pattern-field]').element as HTMLInputElement).value).toBe('name')
    expect((wrapper.find('[data-pattern-value]').element as HTMLInputElement).value).toBe('vendor')
  })

  it('drops patterns with an empty pattern during normalization', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          ...cloneOptions().licenses,
          add_proprietary: true,
          add_patterns: [
            { field: 'name', pattern: '' },
            { field: 'name', pattern: 'vendor' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })

  it('saves normalized non-empty patterns', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          ...cloneOptions().licenses,
          add_proprietary: true,
          add_patterns: [
            { field: ' name ', pattern: ' vendor ' },
            { field: '', pattern: 'ignored' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })

  it('sends normalized patterns with the fix request', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)
    await wrapper.find('[data-pattern-field]').setValue(' name ')
    await wrapper.find('[data-pattern-value]').setValue(' vendor ')
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    const sentOptions = fixSbomMock.mock.calls[0][1] as SbomFixOptions
    expect(sentOptions.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })

  it('restores defaults for the licenses card', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          filter_non_proprietary: true,
          add_proprietary: true,
          remove_proprietary_source_references: true,
          add_patterns: [{ field: 'name', pattern: 'vendor' }],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.reset-defaults').trigger('click')
    for (const id of LICENSES_RULES.map((rule) => rule.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
    const rows = wrapper.findAll('[data-group="licenses"] [data-pattern-row]')
    expect(rows).toHaveLength(1)
    expect((rows[0].find('[data-pattern-field]').element as HTMLInputElement).value).toBe('')
  })

  it('restores defaults without saving them', async () => {
    const wrapper = await mountFixer()

    await wrapper.find('.group-card[data-group="basic"] .clear-all').trigger('click')
    await wrapper.find('.spec-version-input').setValue('1.6')
    await wrapper.find('.reset-defaults').trigger('click')

    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find(rule('components.fill_missing_gost_properties')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('add_manufacturer')).element as HTMLInputElement).checked).toBe(true)
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

    await wrapper.find(rule('reorder')).setValue(false)
    await flushPromises()
    expect(wrapper.find('.save-status').text()).not.toContain('Saved')

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).toContain('Saved')

    await selectFile(wrapper)
    expect(wrapper.find('.save-status').text()).not.toContain('Saved')
  })

  it('clears the Saved status when a pattern row changes', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).toContain('Saved')

    await wrapper.find('[data-pattern-field]').setValue('name')
    await flushPromises()
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
    await wrapper.find(rule('set_spec_version')).setValue(false)
    expect((wrapper.find('.spec-version-input').element as HTMLInputElement).disabled).toBe(true)
  })

  it('disables the manufacturer input when add_manufacturer is off and saves its value', async () => {
    const wrapper = await mountFixer()

    const input = () => wrapper.find('.manufacturer-input')
    expect((input().element as HTMLInputElement).value).toBe('Positive Technologies')
    expect((input().element as HTMLInputElement).disabled).toBe(false)

    await input().setValue('ООО Ромашка')
    await wrapper.find(rule('add_manufacturer')).setValue(false)
    expect((input().element as HTMLInputElement).disabled).toBe(true)

    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()

    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.manufacturer).toBe('ООО Ромашка')
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
    expect(fixSbomMock).toHaveBeenCalledWith(file, cloneOptions(), [])
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

    await wrapper.find(rule('reorder')).setValue(false)
    await selectFile(wrapper, 'other.json')

    expect(wrapper.find('.status-card').exists()).toBe(false)
    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(false)
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
    expect(rows[0].text()).toContain('Reorder fields')
    expect(rows[0].text()).toContain('2')
    expect(rows[1].text()).toContain('Keep only GOST properties')
    expect(rows[1].text()).toContain('0')
  })

  it('renders a removal stat row with its field path', async () => {
    fixSbomMock.mockResolvedValueOnce(statsWithFieldResponse)
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('.stats-table tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('components[].scope')
    expect(rows[0].text()).toContain('3')
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
    expect(rows[0].findAll('td')[0].attributes('title')).toBeUndefined()
    expect(rows[1].text()).toContain('specVersion')
    expect(rows[1].text()).toContain('{"expected":"1.6 or 1.7"}')
  })

  it('renders long issue values in full without truncation attributes', async () => {
    const longPath = '$.components[0].components[1].components[2].components[3]'
    const longName = 'very-long-component-name-without-any-break-opportunities'
    fixSbomMock.mockResolvedValueOnce({
      ...issuesResponse,
      issues: [
        {
          code: 'component.missing_name',
          path: longPath,
          component: longName,
          details: { expected: 'a-very-long-value-that-must-remain-visible' },
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

    const cells = wrapper.findAll('.issues-table tbody tr td')
    expect(cells[1].text()).toBe(longPath)
    expect(cells[2].text()).toBe(longName)
    expect(cells[3].text()).toBe('{"expected":"a-very-long-value-that-must-remain-visible"}')
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

  it('analyzes the file and renders unchecked candidates', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [
        { path: 'root.dependencies', status: 'additional', count: 1 },
        { path: 'root.version', status: 'mandatory', count: 1 },
        { path: 'components[].scope', status: 'additional', count: 3 },
        { path: 'components[].group', status: 'additional', count: 2 },
      ],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()

    expect(analyzeSbomMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-field="root.dependencies"]').exists()).toBe(true)
    expect(wrapper.find('[data-field="components[].scope"]').exists()).toBe(true)
    expect(wrapper.find('[data-field="root.version"]').exists()).toBe(false)
    expect(wrapper.find('[data-field="components[].group"]').exists()).toBe(false)

    expect(wrapper.find('[data-field="root.dependencies"]').text()).toContain('1')
    expect(wrapper.find('[data-field="components[].scope"]').text()).toContain('3')

    const checkboxes = wrapper.findAll('[data-remove-field]')
    expect(checkboxes).toHaveLength(2)
    for (const checkbox of checkboxes) {
      expect((checkbox.element as HTMLInputElement).checked).toBe(false)
    }
  })

  it('recomputes candidates immediately when the keep list is edited', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [
        { path: 'components[].group', status: 'additional', count: 2 },
        { path: 'components[].scope', status: 'additional', count: 3 },
      ],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-field="components[].group"]').exists()).toBe(false)

    const keep = defaultOptions.optional_fields.keep.filter((p) => p !== 'components[].group')
    await wrapper.find('textarea[data-role="keep-list"]').setValue(keep.join('\n'))
    await flushPromises()

    expect(wrapper.find('[data-field="components[].group"]').exists()).toBe(true)
    expect(analyzeSbomMock).toHaveBeenCalledTimes(1)
  })

  it('drops a selected path when it is added to the keep list', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [{ path: 'components[].scope', status: 'additional', count: 3 }],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-remove-field="components[].scope"]').setValue(true)
    await flushPromises()

    const keep = [...defaultOptions.optional_fields.keep, 'components[].scope']
    await wrapper.find('textarea[data-role="keep-list"]').setValue(keep.join('\n'))
    await flushPromises()

    expect(wrapper.find('[data-field="components[].scope"]').exists()).toBe(false)
  })

  it('sends only selected candidates as remove_fields', async () => {
    const wrapper = await mountFixer()
    const file = await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [
        { path: 'root.dependencies', status: 'additional', count: 1 },
        { path: 'components[].scope', status: 'additional', count: 3 },
      ],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-remove-field="root.dependencies"]').setValue(true)
    await flushPromises()

    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()

    expect(fixSbomMock).toHaveBeenCalledWith(file, cloneOptions(), ['root.dependencies'])
  })

  it('select all and clear all only affect candidates', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [
        { path: 'root.dependencies', status: 'additional', count: 1 },
        { path: 'root.version', status: 'mandatory', count: 1 },
        { path: 'components[].scope', status: 'additional', count: 3 },
      ],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-action="select-all-fields"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-remove-field]')).toHaveLength(2)
    for (const checkbox of wrapper.findAll('[data-remove-field]')) {
      expect((checkbox.element as HTMLInputElement).checked).toBe(true)
    }

    await wrapper.find('[data-action="clear-all-fields"]').trigger('click')
    await flushPromises()
    for (const checkbox of wrapper.findAll('[data-remove-field]')) {
      expect((checkbox.element as HTMLInputElement).checked).toBe(false)
    }

    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)
  })

  it('renders the read-only fstec list with statuses', async () => {
    getFieldCatalogMock.mockResolvedValueOnce({
      fstec_fields: [
        { path: 'root.bomFormat', status: 'mandatory' },
        { path: 'root.serialNumber', status: 'optional' },
      ],
      default_keep: [...defaultOptions.optional_fields.keep],
    })
    const wrapper = await mountFixer()

    const details = wrapper.find('details[data-role="fstec-list"]')
    expect(details.exists()).toBe(true)
    expect((details.element as HTMLDetailsElement).open).toBe(false)

    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('toggle')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-fstec-path="root.bomFormat"]').exists()).toBe(true)
    expect(wrapper.find('[data-fstec-path="root.serialNumber"]').exists()).toBe(true)
    expect(wrapper.find('[data-fstec-path="root.bomFormat"]').text()).toContain('Mandatory')
    expect(wrapper.find('[data-fstec-path="root.serialNumber"]').text()).toContain('Optional')
  })

  it('reset defaults restores the ten keep paths and static options', async () => {
    const wrapper = await mountFixer()

    await wrapper.find('.group-card[data-group="basic"] .clear-all').trigger('click')
    await wrapper.find('textarea[data-role="keep-list"]').setValue('')
    await wrapper.find('.reset-defaults').trigger('click')
    await flushPromises()

    expect((wrapper.find(rule('reorder')).element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find('.manufacturer-input').element as HTMLInputElement).value).toBe(
      'Positive Technologies',
    )
    expect(
      (wrapper.find('textarea[data-role="keep-list"]').element as HTMLTextAreaElement).value,
    ).toBe(defaultOptions.optional_fields.keep.join('\n'))
  })

  it('new file selection resets analysis and selection', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [{ path: 'root.dependencies', status: 'additional', count: 1 }],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-remove-field="root.dependencies"]').setValue(true)
    await flushPromises()
    expect(wrapper.find('[data-field="root.dependencies"]').exists()).toBe(true)

    await selectFile(wrapper, 'other.json')

    expect(wrapper.find('[data-field="root.dependencies"]').exists()).toBe(false)
  })

  it('clears stale candidates when a re-analyze fails', async () => {
    const wrapper = await mountFixer()
    await selectFile(wrapper)
    analyzeSbomMock.mockResolvedValueOnce({
      fields: [{ path: 'root.dependencies', status: 'additional', count: 1 }],
    })
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-field="root.dependencies"]').exists()).toBe(true)

    analyzeSbomMock.mockRejectedValueOnce(new ApiError(400, 'invalid_sbom'))
    await wrapper.find('[data-action="analyze"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-field="root.dependencies"]').exists()).toBe(false)
    expect(wrapper.find('.error-msg').exists()).toBe(true)
  })

  it('catalog failure does not block the page and keeps the list on reset', async () => {
    getFieldCatalogMock.mockRejectedValueOnce(new Error('catalog down'))
    const wrapper = await mountFixer()

    expect(wrapper.find('.group-card').exists()).toBe(true)
    expect(wrapper.find('.catalog-warning').exists()).toBe(true)

    const textarea = () => wrapper.find('textarea[data-role="keep-list"]')
    await textarea().setValue('components[].group')
    const before = (textarea().element as HTMLTextAreaElement).value

    await wrapper.find('.reset-defaults').trigger('click')
    await flushPromises()

    expect((textarea().element as HTMLTextAreaElement).value).toBe(before)
  })

  it('renders the provided_by editor with the Astra default row', async () => {
    const wrapper = await mountFixer()
    const rows = wrapper.findAll(
      '[data-group="components"] [data-provided-by-row]',
    )
    expect(rows).toHaveLength(1)
    expect(
      (rows[0].find('[data-provided-by-field]').element as HTMLInputElement).value,
    ).toBe('purl')
    expect(
      (rows[0].find('[data-provided-by-value]').element as HTMLInputElement).value,
    ).toBe('pkg:deb/astra')
    expect(
      (rows[0].find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toContain('Astra Linux Special Edition')
  })

  it('fills provided_by rows from the loaded options', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        components: {
          ...cloneOptions().components,
          provided_by_patterns: [
            { field: 'name', pattern: 'vendor', provided_by: 'Vendor SZI' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    const row = wrapper.find('[data-group="components"] [data-provided-by-row]')
    expect(
      (row.find('[data-provided-by-field]').element as HTMLInputElement).value,
    ).toBe('name')
    expect(
      (row.find('[data-provided-by-value]').element as HTMLInputElement).value,
    ).toBe('vendor')
    expect(
      (row.find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toBe('Vendor SZI')
  })

  it('adds and removes provided_by rows', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-action="add-provided-by"]').trigger('click')
    expect(
      wrapper.findAll('[data-group="components"] [data-provided-by-row]'),
    ).toHaveLength(2)
    await wrapper
      .findAll('[data-action="remove-provided-by"]')[1]
      .trigger('click')
    expect(
      wrapper.findAll('[data-group="components"] [data-provided-by-row]'),
    ).toHaveLength(1)
  })

  it('disables the provided_by editor while the rule is off', async () => {
    const wrapper = await mountFixer()
    expect(
      wrapper.find('[data-provided-by-field]').attributes('disabled'),
    ).toBeUndefined()
    await wrapper.find(rule('components.add_provided_by')).setValue(false)
    expect(
      wrapper.find('[data-provided-by-field]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-provided-by-value]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-provided-by-name]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-action="add-provided-by"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-action="remove-provided-by"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('keeps provided_by values when the rule is turned off', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-provided-by-name]').setValue('Vendor SZI')
    await wrapper.find(rule('components.add_provided_by')).setValue(false)
    expect(
      (wrapper.find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toBe('Vendor SZI')
  })

  it('normalizes provided_by rows and drops incomplete ones', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        components: {
          ...cloneOptions().components,
          provided_by_patterns: [
            { field: ' name ', pattern: ' vendor ', provided_by: ' SZI ' },
            { field: '', pattern: 'x', provided_by: 'ignored' },
            { field: 'purl', pattern: 'pkg:deb/astra', provided_by: '' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.components.provided_by_patterns).toEqual([
      { field: 'name', pattern: 'vendor', provided_by: 'SZI' },
    ])
  })

  it('sends provided_by options with the fix request', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-provided-by-name]').setValue('Vendor SZI')
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    const sent = fixSbomMock.mock.calls[0][1] as SbomFixOptions
    expect(sent.components.provided_by_patterns).toEqual([
      {
        field: 'purl',
        pattern: 'pkg:deb/astra',
        provided_by: 'Vendor SZI',
      },
    ])
  })

  it('restores the Astra provided_by row on reset', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-provided-by-field]').setValue('name')
    await wrapper.find('.reset-defaults').trigger('click')
    const row = wrapper.find('[data-group="components"] [data-provided-by-row]')
    expect(
      (row.find('[data-provided-by-field]').element as HTMLInputElement).value,
    ).toBe('purl')
    expect(
      (row.find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toContain('Astra Linux Special Edition')
  })

  it('clears the Saved status when a provided_by row changes', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).toContain('Saved')
    await wrapper.find('[data-provided-by-name]').setValue('Vendor SZI')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).not.toContain('Saved')
  })
})
