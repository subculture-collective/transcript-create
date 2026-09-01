import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminEvents from '../routes/admin/AdminEvents';
import { http } from '../services/api';

describe('AdminEvents', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('filters events, renders summaries and rows, and exports the active filter set', async () => {
    const getMock = vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'admin/events/summary') {
        return {
          json: vi.fn().mockResolvedValue({
            by_type: [{ type: 'search', count: 4 }],
            by_day: [{ day: '2026-08-06', count: 7 }],
          }),
        } as never;
      }
      return {
        json: vi.fn().mockResolvedValue({
          items: [
            {
              id: 42,
              created_at: '2026-08-06T12:00:00Z',
              user_id: null,
              type: 'search',
              payload: { query: 'housing' },
            },
          ],
        }),
      } as never;
    }) as never);
    const user = userEvent.setup();

    render(<AdminEvents />);

    expect(await screen.findByText(/housing/)).toBeInTheDocument();
    expect(screen.getByText('anon')).toBeInTheDocument();
    expect(screen.getByText('2026-08-06')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Type'), 'search');
    await user.type(screen.getByLabelText('User Email'), 'person@example.com');
    await user.type(screen.getByLabelText('Start'), '2026-08-01T00:00');
    await user.type(screen.getByLabelText('End'), '2026-08-06T23:59');
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith(
        'admin/events',
        expect.objectContaining({ searchParams: expect.any(URLSearchParams) })
      );
    });
    const eventCall = [...getMock.mock.calls].reverse().find(([path]) => path === 'admin/events');
    const eventParams = eventCall?.[1]?.searchParams as URLSearchParams;
    expect(Object.fromEntries(eventParams)).toEqual({
      type: 'search',
      user_email: 'person@example.com',
      start: '2026-08-01T00:00',
      end: '2026-08-06T23:59',
      limit: '25',
      offset: '0',
    });

    const exportUrl = new URL(
      screen.getByRole('link', { name: 'Export CSV' }).getAttribute('href')!,
      'http://localhost'
    );
    expect(exportUrl.pathname).toContain('admin/events.csv');
    expect(Object.fromEntries(exportUrl.searchParams)).toEqual({
      type: 'search',
      user_email: 'person@example.com',
      start: '2026-08-01T00:00',
      end: '2026-08-06T23:59',
    });
  }, 15_000);
});
