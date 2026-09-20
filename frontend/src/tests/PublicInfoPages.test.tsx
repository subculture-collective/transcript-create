import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import axe from 'axe-core';
import AboutPage from '../routes/AboutPage';
import { PrivacyPage, TermsPage } from '../routes/PolicyPages';

describe('public project pages', () => {
  it('describes the archive method and independence clearly', async () => {
    const { container } = render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>
    );

    expect(
      screen.getByRole('heading', { name: 'A broadcast archive built like a public record.' })
    ).toBeInTheDocument();
    expect(screen.getByText(/Source recordings and trademarks belong/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Search the archive/ })).toHaveAttribute(
      'href',
      '/search'
    );
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('publishes privacy and donation terms before accepting support', () => {
    const { unmount } = render(<PrivacyPage />, { wrapper: MemoryRouter });
    expect(screen.getByRole('heading', { name: 'Privacy' })).toBeInTheDocument();
    expect(screen.getByText(/Stripe receives payment information/i)).toBeInTheDocument();
    unmount();

    render(<TermsPage />, { wrapper: MemoryRouter });
    expect(screen.getByRole('heading', { name: 'Terms' })).toBeInTheDocument();
    expect(screen.getByText(/donations are voluntary/i)).toBeInTheDocument();
  });
});
