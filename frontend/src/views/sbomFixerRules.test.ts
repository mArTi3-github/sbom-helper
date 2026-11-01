import { describe, it, expect } from 'vitest'
import ru from '../i18n/locales/ru.json'
import en from '../i18n/locales/en.json'
import { ALL_FIX_RULES, BASE_RULES, COMPONENTS_RULES, LICENSES_RULES } from './sbomFixerRules'

function lookup(messages: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, part) => {
    if (typeof acc !== 'object' || acc === null) return undefined
    return (acc as Record<string, unknown>)[part]
  }, messages)
}

const GROUPS = [
  { rules: BASE_RULES, prefix: '', size: 5, flat: true },
  { rules: COMPONENTS_RULES, prefix: 'components.', size: 3, flat: false },
  { rules: LICENSES_RULES, prefix: 'licenses.', size: 3, flat: false },
]

describe('sbomFixerRules catalog', () => {
  it('covers all 11 rules with unique ids', () => {
    expect(ALL_FIX_RULES).toHaveLength(11)
    expect(new Set(ALL_FIX_RULES.map((rule) => rule.id)).size).toBe(11)
    for (const rule of ALL_FIX_RULES) {
      expect(rule.key, rule.id).toBe(rule.id.split('.').pop())
    }
  })

  it('adds add_manufacturer and drops removal rules', () => {
    const ids = ALL_FIX_RULES.map((rule) => rule.id)
    expect(ids).toContain('add_manufacturer')
    for (const id of [
      'root.remove_dependencies', 'root.remove_services',
      'metadata.remove_properties', 'metadata.remove_tools',
      'metadata_component.remove_external_references', 'metadata_component.remove_purl',
      'metadata_component.remove_properties',
      'metadata_component.remove_scope',
      'components.remove_hashes', 'components.remove_scope',
    ]) {
      expect(ids).not.toContain(id)
    }
  })

  it('starts the base group with the merged reorder rule', () => {
    expect(BASE_RULES[0].id).toBe('reorder')
    for (const group of GROUPS) {
      expect(group.rules).toHaveLength(group.size)
      for (const rule of group.rules) {
        expect(rule.id.startsWith(group.prefix), rule.id).toBe(true)
        if (group.flat) {
          expect(rule.id.includes('.'), rule.id).toBe(false)
        }
      }
    }
    expect(COMPONENTS_RULES[0].id).toBe('components.filter_external_references')
    expect(LICENSES_RULES.map((rule) => rule.id)).toEqual([
      'licenses.filter_non_proprietary',
      'licenses.add_proprietary',
      'licenses.remove_proprietary_source_references',
    ])
  })

  it('provides valid JSON examples that actually differ', () => {
    for (const rule of ALL_FIX_RULES) {
      expect(() => JSON.parse(rule.example.before), rule.id).not.toThrow()
      expect(() => JSON.parse(rule.example.after), rule.id).not.toThrow()
      expect(rule.example.before, rule.id).not.toBe(rule.example.after)
    }
  })

  it('has labels and help texts in both locales for every rule', () => {
    for (const locale of [ru, en]) {
      for (const rule of ALL_FIX_RULES) {
        const label = lookup(locale, `sbomFixer.rules.${rule.id}`)
        const help = lookup(locale, `sbomFixer.help.${rule.id}`)
        expect(typeof label, rule.id).toBe('string')
        expect((label as string).length, rule.id).toBeGreaterThan(0)
        expect(typeof help, rule.id).toBe('string')
        expect((help as string).length, rule.id).toBeGreaterThan(20)
      }
    }
  })

  it('has example labels in both locales', () => {
    for (const locale of [ru, en]) {
      expect(lookup(locale, 'sbomFixer.exampleBefore')).toBeTruthy()
      expect(lookup(locale, 'sbomFixer.exampleAfter')).toBeTruthy()
    }
  })

  it('removes the obsolete warning message from both locales', () => {
    expect(lookup(ru, 'sbomFixer.warning')).toBeUndefined()
    expect(lookup(en, 'sbomFixer.warning')).toBeUndefined()
  })
})
