import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SearchPage from '../routes/SearchPage'
import { renderWithProviders } from './test-utils'
import { http } from '../services/api'

vi.mock('../services', async () => {
  const actual = await vi.importActual('../services')
  return {
    ...actual,
    track: vi.fn(),
  }
})

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useSearchParams: vi.fn(() => {
      const params = new URLSearchParams()
      const setParams = vi.fn()
      return [params, setParams]
    }),
    Link: ({ to, children, ...props }: any) => <a href={to} {...props}>{children}</a>,
  }
})

describe('SearchPage Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Mock auth/me
    const getMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ user: null }),
    })
    vi.spyOn(http, 'get').mockImplementation(getMock)
  })

  it('renders search form with input and button', async () => {
    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search transcripts…')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument()
    expect(screen.getByText('Our Transcript')).toBeInTheDocument()
    expect(screen.getByText('YouTube Auto-Captions')).toBeInTheDocument()
  })

  it('shows prompt when no query is entered', async () => {
    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      expect(screen.getByText('Enter a query to search.')).toBeInTheDocument()
    })
  })

  it('disables search button when query is empty', async () => {
    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      const searchButton = screen.getByRole('button', { name: /search/i })
      expect(searchButton).toBeDisabled()
    })
  })

  it('enables search button when query is entered', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search transcripts…')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Search transcripts…')
    await user.type(input, 'test query')

    const searchButton = screen.getByRole('button', { name: /search/i })
    expect(searchButton).not.toBeDisabled()
  })

  it('updates input value when typing', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search transcripts…')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Search transcripts…') as HTMLInputElement
    await user.type(input, 'test query')

    expect(input.value).toBe('test query')
  })

  it('changes search source between native and youtube', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search transcripts…')).toBeInTheDocument()
    })

    const select = screen.getByDisplayValue('Our Transcript')
    expect(select).toBeInTheDocument()

    await user.selectOptions(select, 'youtube')
    expect(screen.getByDisplayValue('YouTube Auto-Captions')).toBeInTheDocument()
  })
})
