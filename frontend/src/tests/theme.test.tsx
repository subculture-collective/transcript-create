import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

// Mock localStorage before importing theme
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  clear: vi.fn(),
  removeItem: vi.fn(),
  length: 0,
  key: vi.fn(),
}

Object.defineProperty(globalThis, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
})

// Now import theme after mocking localStorage
import { ThemeProvider, useTheme } from '../services/theme'

// Test component that uses theme
function TestComponent() {
  const { theme, toggleTheme } = useTheme()

  return (
    <div>
      <div data-testid="theme">{theme}</div>
      <button onClick={toggleTheme}>Toggle Theme</button>
    </div>
  )
}

// Helper to simulate system preference
function mockSystemPreference(isDark: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-color-scheme: dark)' ? isDark : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe('theme service', () => {
  beforeEach(() => {
    // Reset localStorage mocks
    mockLocalStorage.getItem.mockReset()
    mockLocalStorage.setItem.mockReset()

    // Mock document methods
    document.documentElement.classList.remove = vi.fn()
    document.documentElement.classList.add = vi.fn()
    
    // Mock querySelector for meta theme-color
    document.querySelector = vi.fn((selector: string) => {
      if (selector === 'meta[name="theme-color"]') {
        return {
          setAttribute: vi.fn(),
        } as unknown as Element
      }
      return null
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('ThemeProvider', () => {
    it('defaults to system preference when no stored preference exists', () => {
      mockLocalStorage.getItem.mockReturnValue(null)
      mockSystemPreference(true) // System prefers dark

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    })

    it('uses stored preference over system preference', () => {
      mockLocalStorage.getItem.mockReturnValue('light') // User set light
      mockSystemPreference(true) // System prefers dark

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('theme')).toHaveTextContent('light')
    })

    it('toggles theme and stores preference', () => {
      mockLocalStorage.getItem.mockReturnValue(null)
      mockSystemPreference(false) // System prefers light

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('theme')).toHaveTextContent('light')

      // Click toggle button
      act(() => {
        screen.getByText('Toggle Theme').click()
      })

      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('themePreference', 'dark')
    })

    it('does not auto-switch after manual toggle', () => {
      mockLocalStorage.getItem.mockReturnValue(null)
      
      // Start with system preference
      const listeners: Array<(e: MediaQueryListEvent) => void> = []
      
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation((query: string) => ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: vi.fn((event: string, handler: (e: MediaQueryListEvent) => void) => {
            if (event === 'change') {
              listeners.push(handler)
            }
          }),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      })

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('theme')).toHaveTextContent('light')

      // User manually toggles
      act(() => {
        screen.getByText('Toggle Theme').click()
      })

      expect(screen.getByTestId('theme')).toHaveTextContent('dark')

      // System preference changes
      act(() => {
        listeners.forEach(listener => {
          listener({ matches: true } as MediaQueryListEvent)
        })
      })

      // Theme should NOT change because user manually set it
      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    })

    it('auto-switches when preference is "auto"', () => {
      mockLocalStorage.getItem.mockReturnValue(null) // No stored preference means "auto"
      
      const listeners: Array<(e: MediaQueryListEvent) => void> = []
      
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation((query: string) => ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: vi.fn((event: string, handler: (e: MediaQueryListEvent) => void) => {
            if (event === 'change') {
              listeners.push(handler)
            }
          }),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      })

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('theme')).toHaveTextContent('light')

      // System preference changes to dark
      act(() => {
        listeners.forEach(listener => {
          listener({ matches: true } as MediaQueryListEvent)
        })
      })

      // Theme SHOULD change because user hasn't manually set a preference
      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    })

    it('applies theme classes to document element', () => {
      mockLocalStorage.getItem.mockReturnValue(null)
      mockSystemPreference(false)

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(document.documentElement.classList.remove).toHaveBeenCalledWith('light', 'dark')
      expect(document.documentElement.classList.add).toHaveBeenCalledWith('light')
    })

    it('updates meta theme-color', () => {
      mockLocalStorage.getItem.mockReturnValue(null)
      mockSystemPreference(true)
      const mockMeta = {
        setAttribute: vi.fn(),
      }
      
      document.querySelector = vi.fn((selector: string) => {
        if (selector === 'meta[name="theme-color"]') {
          return mockMeta as unknown as Element
        }
        return null
      })

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(mockMeta.setAttribute).toHaveBeenCalledWith('content', '#0c0a09')
    })
  })
})
