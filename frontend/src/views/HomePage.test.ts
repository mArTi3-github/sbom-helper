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

  it('renders all 5 section tiles', () => {
    const wrapper = mountWithI18n(HomePage)
    const tiles = wrapper.findAll('.tile')
    expect(tiles).toHaveLength(5)
  })

  it('renders correct titles for each tile', () => {
    const wrapper = mountWithI18n(HomePage)
    const tiles = wrapper.findAll('.tile-title')
    expect(tiles[0].text()).toBe('Resolve PURL')
    expect(tiles[1].text()).toBe('Enrich SBOM')
    expect(tiles[2].text()).toBe('Generate Images List')
    expect(tiles[3].text()).toBe('Manage Database')
    expect(tiles[4].text()).toBe('Settings')
  })

  it('each tile links to the correct route', () => {
    const wrapper = mountWithI18n(HomePage)
    const links = wrapper.findAll('.tile')
    const expectedRoutes = [
      '/purl-resolver',
      '/sbom-updater',
      '/images-list-converter',
      '/db-admin',
      '/settings',
    ]
    links.forEach((link, i) => {
      expect(link.attributes('to')).toBe(expectedRoutes[i])
    })
  })
})
