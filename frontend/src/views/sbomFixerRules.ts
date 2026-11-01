import type { ComponentsFixOptions, LicensesFixOptions } from '../types/api'

export interface FixRuleExample {
  readonly before: string
  readonly after: string
}

export interface FixRule<K extends string> {
  readonly id: string
  readonly key: K
  readonly example: FixRuleExample
}

export type BaseRuleKey =
  | 'reorder'
  | 'set_spec_version'
  | 'increment_version'
  | 'add_timestamp'
  | 'add_manufacturer'
export type ComponentsRuleKey = keyof ComponentsFixOptions

export const BASE_RULES: readonly FixRule<BaseRuleKey>[] = [
  {
    id: 'reorder',
    key: 'reorder',
    example: {
      before: `{
  "components": [
    { "purl": "pkg:npm/left-pad@1.3.0", "name": "left-pad", "type": "library" }
  ],
  "metadata": {
    "component": { "name": "app", "type": "application" },
    "timestamp": "2026-10-29T12:00:00Z"
  },
  "bomFormat": "CycloneDX"
}`,
      after: `{
  "bomFormat": "CycloneDX",
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "component": { "type": "application", "name": "app" }
  },
  "components": [
    { "type": "library", "name": "left-pad", "purl": "pkg:npm/left-pad@1.3.0" }
  ]
}`,
    },
  },
  {
    id: 'set_spec_version',
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
    id: 'increment_version',
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
  {
    id: 'add_timestamp',
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
    id: 'add_manufacturer',
    key: 'add_manufacturer',
    example: {
      before: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "version": "1.0.0"
    }
  }
}`,
      after: `{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "version": "1.0.0",
      "manufacturer": { "name": "Positive Technologies" }
    }
  }
}`,
    },
  },
]

export const COMPONENTS_RULES: readonly FixRule<ComponentsRuleKey>[] = [
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

export type LicensesRuleKey = Exclude<keyof LicensesFixOptions, 'add_patterns'>

export const LICENSES_RULES: readonly FixRule<LicensesRuleKey>[] = [
  {
    id: 'licenses.filter_non_proprietary',
    key: 'filter_non_proprietary',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "licenses": [
        { "license": { "name": "MIT" } }
      ]
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0"
    }
  ]
}`,
    },
  },
  {
    id: 'licenses.add_proprietary',
    key: 'add_proprietary',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "vendor-tool",
      "version": "2.0.0"
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "vendor-tool",
      "version": "2.0.0",
      "licenses": [
        { "license": { "name": "Proprietary" } }
      ]
    }
  ]
}`,
    },
  },
  {
    id: 'licenses.remove_proprietary_source_references',
    key: 'remove_proprietary_source_references',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "vendor-tool",
      "version": "2.0.0",
      "licenses": [
        { "license": { "name": "Proprietary" } }
      ],
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/vendor/tool" },
        { "type": "source-distribution", "url": "https://vendor.example.com/tool.tar.gz" }
      ]
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "vendor-tool",
      "version": "2.0.0",
      "licenses": [
        { "license": { "name": "Proprietary" } }
      ],
      "externalReferences": []
    }
  ]
}`,
    },
  },
]

export const ALL_FIX_RULES: readonly FixRule<string>[] = [
  ...BASE_RULES,
  ...COMPONENTS_RULES,
  ...LICENSES_RULES,
]
