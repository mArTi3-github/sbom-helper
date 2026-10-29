import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleHelp from './RuleHelp.vue'

const baseProps = {
  ruleId: 'components.remove_hashes',
  description: 'Removes direct hashes.',
  before: '{\n  "hashes": []\n}',
  after: '{\n}',
  beforeLabel: 'Before',
  afterLabel: 'After',
  ruleTitle: 'Remove hashes',
  open: false,
}

function mountRuleHelp(overrides: Partial<typeof baseProps> = {}) {
  return mount(RuleHelp as any, { props: { ...baseProps, ...overrides } })
}

describe('RuleHelp', () => {
  it('renders only the button when closed', () => {
    const wrapper = mountRuleHelp()
    const button = wrapper.find('.rule-help-button')
    expect(button.exists()).toBe(true)
    expect(button.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.rule-help-panel').exists()).toBe(false)
  })

  it('renders description and both examples when open', () => {
    const wrapper = mountRuleHelp({ open: true })
    const panel = wrapper.find('.rule-help-panel')
    expect(panel.text()).toContain('Removes direct hashes.')
    expect(panel.text()).toContain('Before')
    expect(panel.text()).toContain('After')
    expect(panel.findAll('pre')).toHaveLength(2)
    expect(panel.findAll('pre')[0].text()).toBe(baseProps.before)
    expect(panel.findAll('pre')[1].text()).toBe(baseProps.after)
    expect(wrapper.find('.rule-help-button').attributes('aria-expanded')).toBe('true')
  })

  it('links the button and the panel with aria attributes', () => {
    const wrapper = mountRuleHelp({ open: true })
    const button = wrapper.find('.rule-help-button')
    const panel = wrapper.find('.rule-help-panel')
    expect(button.attributes('aria-controls')).toBe(panel.attributes('id'))
    expect(panel.attributes('aria-labelledby')).toBe(button.attributes('id'))
    expect(panel.attributes('role')).toBe('region')
  })

  it('emits toggle on button click', async () => {
    const wrapper = mountRuleHelp()
    await wrapper.find('.rule-help-button').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('emits close on Escape', async () => {
    const wrapper = mountRuleHelp({ open: true })
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('exposes the rule id for tests and layout', () => {
    const wrapper = mountRuleHelp()
    expect(wrapper.find('[data-help-for="components.remove_hashes"]').exists()).toBe(true)
  })
})
