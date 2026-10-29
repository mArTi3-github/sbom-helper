import { describe, it, expect } from 'vitest'
import ru from '../i18n/locales/ru.json'
import en from '../i18n/locales/en.json'
import {
  ALL_FIX_RULES,
  COMPONENTS_RULES,
  METADATA_COMPONENT_RULES,
  METADATA_RULES,
  ROOT_RULES,
} from './sbomFixerRules'

function lookup(messages: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, part) => {
    if (typeof acc !== 'object' || acc === null) return undefined
    return (acc as Record<string, unknown>)[part]
  }, messages)
}

const GROUPS = [
  { rules: ROOT_RULES, prefix: 'root.', size: 5 },
  { rules: METADATA_RULES, prefix: 'metadata.', size: 4 },
  { rules: METADATA_COMPONENT_RULES, prefix: 'metadata_component.', size: 6 },
  { rules: COMPONENTS_RULES, prefix: 'components.', size: 6 },
]

describe('sbomFixerRules catalog', () => {
  it('covers all 21 rules with unique ids', () => {
    expect(ALL_FIX_RULES).toHaveLength(21)
    expect(new Set(ALL_FIX_RULES.map((rule) => rule.id)).size).toBe(21)
    for (const rule of ALL_FIX_RULES) {
      expect(rule.key, rule.id).toBe(rule.id.split('.').pop())
    }
  })

  it('keeps each group complete and starts it with the reorder rule', () => {
    for (const group of GROUPS) {
      expect(group.rules).toHaveLength(group.size)
      expect(group.rules[0].id).toBe(`${group.prefix}reorder`)
      for (const rule of group.rules) {
        expect(rule.id.startsWith(group.prefix), rule.id).toBe(true)
      }
    }
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
