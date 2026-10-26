import { describe, it, expect } from 'vitest'
import { mountWithI18n } from '../tests/i18n'
import HomePage from './HomePage.vue'

describe('HomePage.vue', () => {
  it('renders the hero section with title and subtitle', () => {
    const wrapper = mountWithI18n(HomePage)
    expect(wrapper.find('.hero-title').text()).toBe('sbom-helper')
    expect(wrapper.find('.hero-subtitle').text()).toBe('SBOM enrichment toolkit — resolve Package URLs, enrich CycloneDX SBOMs, manage your resolved PURL database.')
    expect(wrapper.find('.hero-divider').exists()).toBe(true)
  })

  it('renders all 6 section tiles', () => {
    const wrapper = mountWithI18n(HomePage)
    const tiles = wrapper.findAll('.tile')
    expect(tiles).toHaveLength(6)
  })

  it('renders correct titles for each tile', () => {
    const wrapper = mountWithI18n(HomePage)
    const tiles = wrapper.findAll('.tile-title')
    expect(tiles[0].text()).toBe('Resolve PURL')
    expect(tiles[1].text()).toBe('Enrich SBOM')
    expect(tiles[2].text()).toBe('Fix SBOM')
    expect(tiles[3].text()).toBe('Generate Images List')
    expect(tiles[4].text()).toBe('Manage Database')
    expect(tiles[5].text()).toBe('Settings')
  })

  it('each tile links to the correct route', () => {
    const wrapper = mountWithI18n(HomePage)
    const links = wrapper.findAll('.tile')
    const expectedRoutes = [
      '/purl-resolver',
      '/sbom-updater',
      '/fix-sbom',
      '/images-list-converter',
      '/db-admin',
      '/settings',
    ]
    links.forEach((link, i) => {
      expect(link.attributes('to')).toBe(expectedRoutes[i])
    })
  })
})
