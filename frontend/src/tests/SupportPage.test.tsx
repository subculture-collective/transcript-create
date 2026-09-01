import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axe from 'axe-core';
import SupportPage from '../routes/SupportPage';
import { api } from '../services';

describe('SupportPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('explains the funding model and shows a safe unavailable state before activation', async () => {
    vi.spyOn(api, 'getSupportConfig').mockResolvedValue({
      donations_enabled: false,
      payment_url: null,
    });

    const { container } = render(
      <MemoryRouter>
        <SupportPage />
      </MemoryRouter>
    );

    expect(
      await screen.findByRole('heading', { name: 'Keep the public record searchable.' })
    ).toBeInTheDocument();
    expect(screen.getByText(/Donations are not open yet/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Donate securely/ })).not.toBeInTheDocument();
    expect(screen.getByText('Independent project')).toBeInTheDocument();
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('opens the configured Stripe-hosted checkout without sending card data through HasanAra', async () => {
    vi.spyOn(api, 'getSupportConfig').mockResolvedValue({
      donations_enabled: true,
      payment_url: 'https://buy.stripe.com/test_example',
    });

    render(
      <MemoryRouter>
        <SupportPage />
      </MemoryRouter>
    );

    const link = await screen.findByRole('link', { name: /Donate securely with Stripe/ });
    expect(link).toHaveAttribute('href', 'https://buy.stripe.com/test_example');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText(/Card details never touch HasanAra/)).toBeInTheDocument();
  });
});
