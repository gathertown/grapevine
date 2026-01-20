import { createFrontendConfig } from '../eslint.shared.js';
import globals from 'globals';

export default [
  ...createFrontendConfig(),
  // Context files - allow mixed exports
  {
    files: ['src/contexts/*.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  // Test files - Jest configuration
  {
    files: ['src/**/__tests__/**/*.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.jest,
      },
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'off', // Allow any in tests
    },
  },
];
