import { render, RenderOptions } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { ReactElement } from 'react'
import { AuthProvider } from '../services/auth'

/**
 * Custom render function that wraps components with necessary providers
 */
export function renderWithRouter(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, {
    wrapper: ({ children }) => <BrowserRouter>{children}</BrowserRouter>,
    ...options,
  })
}

/**
 * Render with both Router and Auth providers
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, {
    wrapper: ({ children }) => (
      <BrowserRouter>
        <AuthProvider>{children}</AuthProvider>
      </BrowserRouter>
    ),
    ...options,
  })
}

/**
 * Mock API response helper for ky
 */
export function mockAPIResponse(data: any, status = 200) {
  return {
    json: async () => data,
    status,
    ok: status >= 200 && status < 300,
  }
}

/**
 * Mock API error helper
 */
export function mockAPIError(status: number, data?: any) {
  const error: any = new Error('HTTP Error')
  error.response = {
    status,
    json: async () => data || { message: 'Error' },
  }
  return error
}

/**
 * Wait for async operations
 */
export const waitFor = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
