import type {
  ComponentsFixOptions,
  MetadataComponentFixOptions,
  MetadataFixOptions,
  RootFixOptions,
} from '../types/api'

export interface FixRuleExample {
  readonly before: string
  readonly after: string
}

export interface FixRule<K extends string> {
  readonly id: string
  readonly key: K
  readonly example: FixRuleExample
}

export type RootRuleKey = Exclude<keyof RootFixOptions, 'spec_version'>
export type MetadataRuleKey = Exclude<keyof MetadataFixOptions, 'component'>
export type MetadataComponentRuleKey = keyof MetadataComponentFixOptions
export type ComponentsRuleKey = keyof ComponentsFixOptions

export const ROOT_RULES: readonly FixRule<RootRuleKey>[] = [
  {
    id: 'root.reorder',
    key: 'reorder',
    example: {
      before: `{
  "components": [],
  "version": 3,
  "bomFormat": "CycloneDX",
  "specVersion": "1.7"
}`,
      after: `{
  "bomFormat": "CycloneDX",
  "specVersion": "1.7",
  "version": 3,
  "components": []
}`,
    },
  },
  {
    id: 'root.set_spec_version',
    key: 'set_spec_version',
    example: {
      before: `{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5"
}`,
      after: `{
  "bomFormat": "CycloneDX",
  "specVersion": "1.7"
}`,
    },
  },
  {
    id: 'root.remove_dependencies',
    key: 'remove_dependencies',
    example: {
      before: `{
  "bomFormat": "CycloneDX",
  "dependencies": [
    { "ref": "pkg:npm/left-pad@1.3.0" }
  ]
}`,
      after: `{
  "bomFormat": "CycloneDX"
}`,
    },
  },
  {
    id: 'root.remove_services',
    key: 'remove_services',
    example: {
      before: `{
  "bomFormat": "CycloneDX",
  "services": [
    { "name": "auth-api", "version": "1.0.0" }
  ]
}`,
      after: `{
  "bomFormat": "CycloneDX"
}`,
    },
  },
  {
    id: 'root.increment_version',
    key: 'increment_version',
    example: {
      before: `{
  "bomFormat": "CycloneDX",
  "version": 3
}`,
      after: `{
  "bomFormat": "CycloneDX",
  "version": 4
}`,
    },
  },
]

export const METADATA_RULES: readonly FixRule<MetadataRuleKey>[] = [
  {
    id: 'metadata.reorder',
    key: 'reorder',
    example: {
      before: `{
  "metadata": {
    "component": { "name": "app" },
    "timestamp": "2026-10-29T12:00:00Z"
  }
}`,
      after: `{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "component": { "name": "app" }
  }
}`,
    },
  },
  {
    id: 'metadata.add_timestamp',
    key: 'add_timestamp',
    example: {
      before: `{
  "metadata": {
    "component": { "type": "application", "name": "app", "version": "1.0.0" }
  }
}`,
      after: `{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "component": { "type": "application", "name": "app", "version": "1.0.0" }
  }
}`,
    },
  },
  {
    id: 'metadata.remove_properties',
    key: 'remove_properties',
    example: {
      before: `{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "properties": [
      { "name": "GOST:attack_surface", "value": "no" }
    ]
  }
}`,
      after: `{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z"
  }
}`,
    },
  },
  {
    id: 'metadata.remove_tools',
    key: 'remove_tools',
    example: {
      before: `{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "tools": [
      { "vendor": "Acme", "name": "sbom-generator" }
    ]
  }
}`,
      after: `{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z"
  }
}`,
    },
  },
]

export const METADATA_COMPONENT_RULES: readonly FixRule<MetadataComponentRuleKey>[] = [
  {
    id: 'metadata_component.reorder',
    key: 'reorder',
    example: {
      before: `{
  "metadata": {
    "component": {
      "manufacturer": { "name": "ООО Ромашка" },
      "version": "1.0.0",
      "type": "application",
      "name": "app"
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "version": "1.0.0",
      "manufacturer": { "name": "ООО Ромашка" }
    }
  }
}`,
    },
  },
  {
    id: 'metadata_component.remove_external_references',
    key: 'remove_external_references',
    example: {
      before: `{
  "metadata": {
    "component": {
      "name": "app",
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/acme/app" }
      ]
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "name": "app"
    }
  }
}`,
    },
  },
  {
    id: 'metadata_component.remove_properties',
    key: 'remove_properties',
    example: {
      before: `{
  "metadata": {
    "component": {
      "name": "app",
      "properties": [
        { "name": "GOST:security_function", "value": "no" }
      ]
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "name": "app"
    }
  }
}`,
    },
  },
  {
    id: 'metadata_component.remove_purl',
    key: 'remove_purl',
    example: {
      before: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "purl": "pkg:generic/app@1.0.0"
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app"
    }
  }
}`,
    },
  },
  {
    id: 'metadata_component.remove_scope',
    key: 'remove_scope',
    example: {
      before: `{
  "metadata": {
    "component": {
      "name": "app",
      "scope": "required"
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "name": "app"
    }
  }
}`,
    },
  },
  {
    id: 'metadata_component.rename_supplier',
    key: 'rename_supplier',
    example: {
      before: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "supplier": { "name": "ООО Ромашка" }
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "manufacturer": { "name": "ООО Ромашка" }
    }
  }
}`,
    },
  },
]

export const COMPONENTS_RULES: readonly FixRule<ComponentsRuleKey>[] = [
  {
    id: 'components.reorder',
    key: 'reorder',
    example: {
      before: `{
  "components": [
    {
      "properties": [],
      "purl": "pkg:npm/left-pad@1.3.0",
      "name": "left-pad",
      "type": "library",
      "version": "1.3.0"
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "purl": "pkg:npm/left-pad@1.3.0",
      "properties": []
    }
  ]
}`,
    },
  },
  {
    id: 'components.remove_hashes',
    key: 'remove_hashes',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "hashes": [
        { "alg": "SHA-256", "content": "9f86d081884c7d659a2feaa0c55ad015" }
      ]
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0"
    }
  ]
}`,
    },
  },
  {
    id: 'components.remove_scope',
    key: 'remove_scope',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "scope": "required"
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0"
    }
  ]
}`,
    },
  },
  {
    id: 'components.filter_external_references',
    key: 'filter_external_references',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/stevemao/left-pad" },
        { "type": "website", "url": "https://example.com/left-pad" },
        { "type": "source-distribution", "url": "https://registry.npmjs.org/left-pad" }
      ]
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/stevemao/left-pad" },
        { "type": "source-distribution", "url": "https://registry.npmjs.org/left-pad" }
      ]
    }
  ]
}`,
    },
  },
  {
    id: 'components.filter_properties',
    key: 'filter_properties',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" },
        { "name": "internal:owner", "value": "platform-team" }
      ]
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" }
      ]
    }
  ]
}`,
    },
  },
  {
    id: 'components.fill_missing_gost_properties',
    key: 'fill_missing_gost_properties',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" }
      ]
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" },
        { "name": "GOST:security_function", "value": "no" }
      ]
    }
  ]
}`,
    },
  },
]

export const ALL_FIX_RULES: readonly FixRule<string>[] = [
  ...ROOT_RULES,
  ...METADATA_RULES,
  ...METADATA_COMPONENT_RULES,
  ...COMPONENTS_RULES,
]
