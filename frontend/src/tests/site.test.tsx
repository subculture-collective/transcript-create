import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { http } from '../services/api';
import { SiteProvider, useSite } from '../services/site';

function Consumer() {
  const site = useSite();
  return (
    <p>
      {site.name} · {site.creator_name}
    </p>
  );
}
describe('creator configuration', () => {
  it('uses the configured site and creator instead of a fixed archive brand', async () => {
    vi.spyOn(http, 'get').mockReturnValue({
      json: () =>
        Promise.resolve({
          name: 'Creator library',
          creator_name: 'Demo creator',
          description: 'A catalog',
          community_enabled: false,
          public_passages_enabled: false,
        }),
    } as never);
    render(
      <SiteProvider>
        <Consumer />
      </SiteProvider>
    );
    expect(await screen.findByText('Creator library · Demo creator')).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
