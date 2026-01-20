// Jest setup file for admin-frontend tests
import '@testing-library/jest-dom';

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

// Mock config.ts to avoid import.meta.env issues
jest.mock('../lib/config', () => ({
  getConfig: jest.fn(() => ({
    AMPLITUDE_API_KEY: 'test-key',
    WORKOS_CLIENT_ID: 'test-client-id',
    FRONTEND_URL: 'http://localhost:5173',
    BASE_DOMAIN: 'localhost',
    TRELLO_POWER_UP_API_KEY: 'test-trello-api-key',
  })),
  isDevelopment: jest.fn(() => false),
}));
