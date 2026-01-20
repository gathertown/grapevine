import js from '@eslint/js';
import tseslint from '@typescript-eslint/eslint-plugin';
import tsparser from '@typescript-eslint/parser';
import prettierConfig from 'eslint-config-prettier';
import globals from 'globals';
import importPlugin from 'eslint-plugin-import';
import reactPlugin from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import verbNounsPlugin from 'eslint-plugin-verb-nouns';

export const sharedTsRules = {
  '@typescript-eslint/no-unused-vars': [
    'error',
    { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
  ],
  '@typescript-eslint/no-explicit-any': 'error',
  '@typescript-eslint/no-non-null-assertion': 'error',
  '@typescript-eslint/consistent-type-assertions': [
    'error',
    { assertionStyle: 'as', objectLiteralTypeAssertions: 'never' },
  ],
  '@typescript-eslint/no-require-imports': 'error',
};

export const sharedGeneralRules = {
  'no-unused-vars': 'off',
  'prefer-const': 'error',
  'no-var': 'error',
  'object-shorthand': 'error',
  'prefer-template': 'error',
  'import/no-default-export': 'error',
  'import/no-extraneous-dependencies': 'error',
  'import/no-dynamic-require': 'error',
  'import/no-commonjs': 'error',
};

export const sharedReactRules = {
  'react/react-in-jsx-scope': 'off',
  'react/prop-types': 'off',
  'react/jsx-uses-react': 'error',
  'react/jsx-uses-vars': 'error',
  'react-hooks/rules-of-hooks': 'error',
  'react-hooks/exhaustive-deps': 'error',
  'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
};

export const sharedBackendRules = {
  ...sharedTsRules,
  ...sharedGeneralRules,
};

// Shared configuration factory for backend Node.js projects
export function createBackendConfig() {
  return [
    {
      languageOptions: {
        sourceType: 'module',
      },
    },
    js.configs.recommended,
    // ESM config files
    {
      files: ['eslint.config.mjs'],
      languageOptions: {
        ecmaVersion: 2020,
        sourceType: 'module',
        globals: {
          ...globals.node,
        },
      },
    },
    // CommonJS files
    {
      files: ['**/*.cjs'],
      languageOptions: {
        ecmaVersion: 2020,
        sourceType: 'script',
        globals: {
          ...globals.node,
        },
      },
      rules: {
        '@typescript-eslint/no-var-requires': 'off',
        'no-console': 'off',
      },
    },
    {
      files: ['src/**/*.{ts,js}'],
      languageOptions: {
        parser: tsparser,
        parserOptions: {
          ecmaVersion: 2020,
          sourceType: 'module',
          project: './tsconfig.json',
        },
        globals: {
          ...globals.node,
          fetch: 'readonly',
          Blob: 'readonly',
          CryptoKey: 'readonly',
          NodeJS: 'readonly',
        },
      },
      plugins: {
        '@typescript-eslint': tseslint,
        import: importPlugin,
      },
      rules: sharedBackendRules,
    },
    prettierConfig,
    {
      ignores: ['node_modules/**', 'dist/**', '*.js', '!eslint.config.mjs'],
    },
  ];
}

// Shared configuration factory for backend projects with Jest
export function createBackendConfigWithJest() {
  const baseConfig = createBackendConfig();

  // Add Jest-specific configuration
  const jestConfig = {
    files: ['src/**/*.test.{ts,js}', 'src/__tests__/**/*.{ts,js}'],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2020,
        sourceType: 'module',
        project: './tsconfig.test.json',
      },
      globals: {
        ...globals.node,
        ...globals.jest,
        NodeJS: 'readonly',
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
    },
    rules: {
      ...sharedBackendRules,
      '@typescript-eslint/no-explicit-any': 'off', // Allow any in tests
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ], // Allow unused vars with underscore
    },
  };

  // Allow default exports in specific job processor files
  const allowDefaultExports = {
    files: ['src/jobs/**/*.ts'],
    rules: {
      'import/no-default-export': 'off',
    },
  };

  // Insert Jest config and default export config before prettier config
  const withJest = [...baseConfig];
  withJest.splice(-2, 0, jestConfig, allowDefaultExports);
  return withJest;
}

// Shared configuration factory for React frontend projects
export function createFrontendConfig(options = {}) {
  return [
    js.configs.recommended,
    // JavaScript files
    {
      files: ['**/*.{js,jsx}'],
      languageOptions: {
        ecmaVersion: 2020,
        sourceType: 'module',
        parserOptions: { ecmaFeatures: { jsx: true } },
        globals: { ...globals.browser },
      },
      plugins: {
        import: importPlugin,
        react: reactPlugin,
        'react-hooks': reactHooks,
        'react-refresh': reactRefresh,
        'verb-nouns': verbNounsPlugin,
      },
      settings: { react: { version: 'detect' } },
      rules: {
        ...sharedReactRules,
        ...sharedGeneralRules,
        'verb-nouns/no-verb-noun-confusion': 'error',
        'no-unused-vars': [
          'error',
          { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
        ],
      },
    },
    // TypeScript files
    {
      files: ['**/*.{ts,tsx}'],
      languageOptions: {
        parser: tsparser,
        parserOptions: {
          ecmaVersion: 2020,
          sourceType: 'module',
          ecmaFeatures: { jsx: true },
          project: './tsconfig.json',
        },
        globals: { ...globals.browser },
      },
      plugins: {
        '@typescript-eslint': tseslint,
        import: importPlugin,
        react: reactPlugin,
        'react-hooks': reactHooks,
        'react-refresh': reactRefresh,
        'verb-nouns': verbNounsPlugin,
      },
      settings: { react: { version: 'detect' } },
      rules: {
        ...sharedGeneralRules,
        ...sharedTsRules,
        ...sharedReactRules,
        'verb-nouns/no-verb-noun-confusion': 'error',
      },
    },
    // Allow default exports in declaration files
    {
      files: ['**/*.d.ts'],
      rules: { 'import/no-default-export': 'off' },
    },
    prettierConfig,
    {
      ignores: [
        'node_modules/**',
        'dist/**',
        'build/**',
        '*.config.js',
        'vite.config.ts',
        'tsconfig*.json',
      ],
    },
  ];
}
