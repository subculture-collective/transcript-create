import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { http } from '../services/api';
import { SiteProvider, useSite } from '../services/site';
import { ThemeProvider, useTheme } from '../services/theme';
import AboutPage from '../routes/AboutPage';

function Probe() {
  const site = useSite();
  const { toggleTheme, theme } = useTheme();
  return (
    <button onClick={toggleTheme}>
      {site.name} · {theme}
    </button>
  );
}

function mount() {
  return render(
    <MemoryRouter>
      <SiteProvider>
        <ThemeProvider>
          <Probe />
          <AboutPage />
        </ThemeProvider>
      </SiteProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('client branding', () => {
  it('uses neutral identity when configuration is unavailable', async () => {
    vi.spyOn(http, 'get').mockReturnValue({
      json: () => Promise.reject(new Error('offline')),
    } as never);
    mount();
    expect(screen.getByText('About Transcript Archive')).toBeInTheDocument();
    await act(async () => {});
    expect(document.body.textContent).not.toMatch(/HasanAra|HasanAbi|Subcult/);
  });

  it('applies client copy and both palettes without rebuilding, and removes prior theme tokens', async () => {
    vi.spyOn(localStorage, 'getItem').mockReturnValue('dark');
    vi.spyOn(http, 'get').mockReturnValue({
      json: () =>
        Promise.resolve({
          schema_version: 1,
          name: 'Northstar',
          creator_name: 'Studio',
          description: 'Client catalog',
          public_passages_enabled: true,
          community_enabled: false,
          operator_name: 'Studio team',
          operator_url: 'https://example.org',
          project_notice: 'Maintained by the studio.',
          theme: {
            font: 'mono',
            dark: { accent: '#ffaa00', canvas: '#112233', border: '#556677' },
            light: { accent: '#884400', canvas: '#fffdee' },
          },
        }),
    } as never);
    const view = mount();
    expect(await screen.findByText('About Northstar')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Visit Studio team ↗' })).toHaveAttribute(
      'href',
      'https://example.org'
    );
    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue('--color-accent')).toBe('#ffaa00')
    );
    act(() => screen.getByRole('button', { name: 'Northstar · dark' }).click());
    expect(document.documentElement.style.getPropertyValue('--color-accent')).toBe('#884400');
    expect(document.documentElement.style.getPropertyValue('--color-border')).toBe('');
    expect(localStorage.setItem).toHaveBeenCalledWith('themePreference', 'light');
    view.unmount();
    expect(document.documentElement.style.getPropertyValue('--color-accent')).toBe('');
  });

  it('does not accept an unsupported profile version', async () => {
    vi.spyOn(http, 'get').mockReturnValue({
      json: () =>
        Promise.resolve({
          schema_version: 99,
          name: 'Future brand',
          creator_name: 'Future creator',
          description: 'Future',
          public_passages_enabled: true,
          community_enabled: false,
        }),
    } as never);
    mount();
    await act(async () => {});
    expect(screen.getByText('About Transcript Archive')).toBeInTheDocument();
    expect(screen.queryByText('About Future brand')).not.toBeInTheDocument();
  });
});
