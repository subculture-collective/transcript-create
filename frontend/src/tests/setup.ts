import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).localStorage = localStorageMock

// Mock window.location
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (window as any).location
window.location = {
  href: '',
  origin: 'http://localhost:3000',
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any

// Mock clipboard API
Object.defineProperty(navigator, 'clipboard', {
  value: {
    writeText: vi.fn(),
  },
  writable: true,
  configurable: true,
})
