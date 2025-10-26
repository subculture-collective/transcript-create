import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PricingPage from '../routes/PricingPage'
import { renderWithProviders } from './test-utils'
import { http } from '../services/api'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useSearchParams: vi.fn(() => [new URLSearchParams(), vi.fn()]),
    useNavigate: vi.fn(() => vi.fn()),
  }
})

describe('PricingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).location
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    window.location = { href: '' } as any

    // Mock auth/me to return no user by default
    const getMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ user: null }),
    })
    vi.spyOn(http, 'get').mockImplementation(getMock)
  })

  it('renders pricing page title and description', async () => {
    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Pricing')).toBeInTheDocument()
    })

    expect(screen.getByText('Choose a plan that fits your workflow.')).toBeInTheDocument()
  })

  it('displays free plan details', async () => {
    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Free')).toBeInTheDocument()
    })

    expect(screen.getByText('$0')).toBeInTheDocument()
    expect(screen.getByText('5 searches per day')).toBeInTheDocument()
    expect(screen.getByText('Public favorites')).toBeInTheDocument()
    expect(screen.getByText('Previews')).toBeInTheDocument()
  })

  it('displays Pro plan details', async () => {
    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Pro')).toBeInTheDocument()
    })

    expect(screen.getByText('$9.99')).toBeInTheDocument()
    expect(screen.getByText('Unlimited search')).toBeInTheDocument()
    expect(screen.getByText('SRT/VTT/PDF exports')).toBeInTheDocument()
    expect(screen.getByText('Private notes & favorites')).toBeInTheDocument()
    expect(screen.getByText('Topic alerts & offline packs')).toBeInTheDocument()
  })

  it('displays CTA buttons for Pro plan', async () => {
    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Monthly')).toBeInTheDocument()
    })

    expect(screen.getByText('Yearly')).toBeInTheDocument()
    expect(screen.getByText('Manage billing')).toBeInTheDocument()
  })

  it('handles monthly checkout button click', async () => {
    const user = userEvent.setup()
    const postMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ url: 'https://stripe.com/checkout' }),
    })
    vi.spyOn(http, 'post').mockImplementation(postMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Monthly')).toBeInTheDocument()
    })

    const monthlyButton = screen.getByText('Monthly')
    await user.click(monthlyButton)

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('billing/checkout-session', {
        json: { period: 'monthly' },
      })
      expect(window.location.href).toBe('https://stripe.com/checkout')
    })
  })

  it('handles yearly checkout button click', async () => {
    const user = userEvent.setup()
    const postMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ url: 'https://stripe.com/checkout-yearly' }),
    })
    vi.spyOn(http, 'post').mockImplementation(postMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Yearly')).toBeInTheDocument()
    })

    const yearlyButton = screen.getByText('Yearly')
    await user.click(yearlyButton)

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('billing/checkout-session', {
        json: { period: 'yearly' },
      })
      expect(window.location.href).toBe('https://stripe.com/checkout-yearly')
    })
  })

  it('handles manage billing button click', async () => {
    const user = userEvent.setup()
    const getMock = vi.fn()
      .mockReturnValueOnce({
        json: vi.fn().mockResolvedValue({ user: null }),
      })
      .mockReturnValueOnce({
        json: vi.fn().mockResolvedValue({ url: 'https://stripe.com/portal' }),
      })
    vi.spyOn(http, 'get').mockImplementation(getMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Manage billing')).toBeInTheDocument()
    })

    const manageButton = screen.getByText('Manage billing')
    await user.click(manageButton)

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith('billing/portal')
      expect(window.location.href).toBe('https://stripe.com/portal')
    })
  })

  it('shows success message when checkout succeeds', async () => {
    const { useSearchParams } = await import('react-router-dom')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(useSearchParams as any).mockReturnValue([
      new URLSearchParams('success=true'),
      vi.fn(),
    ])

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(
        screen.getByText("Thanks! Your Pro plan will activate shortly.")
      ).toBeInTheDocument()
    })
  })

  it('shows canceled message when checkout is canceled', async () => {
    const { useSearchParams } = await import('react-router-dom')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(useSearchParams as any).mockReturnValue([
      new URLSearchParams('canceled=true'),
      vi.fn(),
    ])

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(
        screen.getByText('Checkout canceled. You can try again anytime.')
      ).toBeInTheDocument()
    })
  })

  it('shows redirect info when redirect parameter is present', async () => {
    const { useSearchParams } = await import('react-router-dom')
    const params = new URLSearchParams('redirect=/v/video123')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(useSearchParams as any).mockReturnValue([params, vi.fn()])

    const getMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ user: { plan: 'free' } }),
    })
    vi.spyOn(http, 'get').mockImplementation(getMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      // Use more flexible text matching
      expect(
        screen.getByText(/After upgrading.*send you back/i)
      ).toBeInTheDocument()
    })
  })

  it('includes redirect in checkout request when present', async () => {
    const user = userEvent.setup()
    const { useSearchParams } = await import('react-router-dom')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(useSearchParams as any).mockReturnValue([
      new URLSearchParams('redirect=/v/video123'),
      vi.fn(),
    ])

    const postMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ url: 'https://stripe.com/checkout' }),
    })
    vi.spyOn(http, 'post').mockImplementation(postMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Monthly')).toBeInTheDocument()
    })

    const monthlyButton = screen.getByText('Monthly')
    await user.click(monthlyButton)

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('billing/checkout-session', {
        json: { period: 'monthly', redirect: '/v/video123' },
      })
    })
  })

  it('handles checkout API errors gracefully', async () => {
    const user = userEvent.setup()
    // Mock alert on window
    const alertMock = vi.fn()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(globalThis as any).alert = alertMock
    
    const getMock = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ user: null }),
    })
    vi.spyOn(http, 'get').mockImplementation(getMock)
    
    const postMock = vi.fn().mockReturnValue({
      json: vi.fn().mockRejectedValue(new Error('Network error')),
    })
    vi.spyOn(http, 'post').mockImplementation(postMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Monthly')).toBeInTheDocument()
    })

    const monthlyButton = screen.getByText('Monthly')
    await user.click(monthlyButton)

    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Billing not available yet.')
    }, { timeout: 2000 })
  })

  it('handles billing portal API errors gracefully', async () => {
    const user = userEvent.setup()
    // Mock alert on window
    const alertMock = vi.fn()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(globalThis as any).alert = alertMock
    
    let callCount = 0
    const getMock = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount === 1) {
        return { json: vi.fn().mockResolvedValue({ user: null }) }
      }
      return { json: vi.fn().mockRejectedValue(new Error('Network error')) }
    })
    vi.spyOn(http, 'get').mockImplementation(getMock)

    renderWithProviders(<PricingPage />)

    await waitFor(() => {
      expect(screen.getByText('Manage billing')).toBeInTheDocument()
    })

    const manageButton = screen.getByText('Manage billing')
    await user.click(manageButton)

    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Billing not available yet.')
    }, { timeout: 2000 })
  })
})
