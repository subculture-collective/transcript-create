import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

function mockJsonResponse<T>(value: T) {
  return {
    json: () => Promise.resolve(value),
  };
}

vi.mock('../services/api', () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

import { http } from '../services/api';
import AdminArchivePeriods from '../routes/admin/AdminArchivePeriods';

const basePeriod = {
  id: 'period-1',
  slug: 'launch-day',
  label: 'Launch Day',
  kind: 'event',
  date_from: '2026-01-01',
  date_to: '2026-01-02',
  description: 'Launch fallout window',
  status: 'published',
  sort_order: 10,
  recurring_month: null,
  recurring_day: null,
  video_count: 3,
  total_duration_seconds: 3661,
  summary: 'First launch window',
  calculated_at: '2026-01-03T12:00:00Z',
} as const;

describe('AdminArchivePeriods', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the list and creates a period', async () => {
    vi.mocked(http.get).mockImplementation(() => mockJsonResponse({ items: [basePeriod] }) as never);
    vi.mocked(http.post).mockImplementation((url: any, options?: any) => {
      if (url === 'admin/archive/periods') {
        return mockJsonResponse({ ...basePeriod, ...(options?.json as object) }) as never;
      }
      if (url === 'admin/archive/periods/seed') {
        return mockJsonResponse({ created: 2, updated: 1 }) as never;
      }
      return mockJsonResponse(basePeriod) as never;
    });

    render(
      <BrowserRouter>
        <AdminArchivePeriods />
      </BrowserRouter>
    );

    expect(await screen.findByText('Archive periods')).toBeInTheDocument();
    expect(screen.getByText('Launch Day')).toBeInTheDocument();
    expect(screen.getByLabelText('Label')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Label'), 'Holiday Window');
    await user.type(screen.getByLabelText('Slug'), 'holiday-window');
    fireEvent.change(screen.getByDisplayValue('event'), { target: { value: 'holiday' } });
    fireEvent.change(screen.getByLabelText('Date from'), { target: { value: '2026-12-24' } });
    fireEvent.change(screen.getByLabelText('Date to'), { target: { value: '2026-12-26' } });
    fireEvent.change(screen.getByLabelText('Recurring month'), { target: { value: '12' } });
    fireEvent.change(screen.getByLabelText('Recurring day'), { target: { value: '25' } });
    await user.type(screen.getByLabelText('Description'), 'Christmas lead-in');
    await user.type(screen.getByLabelText('Sort order'), '25');

    await user.click(screen.getByRole('button', { name: 'Create period' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith(
        'admin/archive/periods',
        expect.objectContaining({
          json: expect.objectContaining({
            label: 'Holiday Window',
            slug: 'holiday-window',
            kind: 'holiday',
            date_from: '2026-12-24',
            date_to: '2026-12-26',
            description: 'Christmas lead-in',
            status: 'published',
            sort_order: 25,
            recurring_month: 12,
            recurring_day: 25,
          }),
        })
      );
    });

    expect(screen.getByText('Created Holiday Window')).toBeInTheDocument();
  });

  it('edits, recalculates, and toggles status', async () => {
    let currentLabel: string = basePeriod.label;
    let currentStatus: 'published' | 'hidden' = 'published';

    vi.mocked(http.get).mockImplementation((url: any) => {
      if (url === 'admin/archive/periods') {
        return mockJsonResponse({
          items: [{ ...basePeriod, label: currentLabel, status: currentStatus }],
        }) as never;
      }
      return mockJsonResponse({ items: [] }) as never;
    });

    vi.mocked(http.patch).mockImplementation((url: any, options?: any) => {
      if (url === 'admin/archive/periods/launch-day') {
        const payload = options?.json as Record<string, unknown> | undefined;
        if (payload?.label) currentLabel = String(payload.label);
        if (payload?.status === 'hidden' || payload?.status === 'published') {
          currentStatus = payload.status as 'published' | 'hidden';
        }
      }
      return mockJsonResponse({ ...basePeriod, label: currentLabel, status: currentStatus }) as never;
    });

    vi.mocked(http.post).mockImplementation((url: any) => {
      if (url === 'admin/archive/periods/launch-day/refresh') {
        return mockJsonResponse({ ...basePeriod, label: currentLabel, status: currentStatus }) as never;
      }
      return mockJsonResponse({ created: 0 }) as never;
    });

    render(
      <BrowserRouter>
        <AdminArchivePeriods />
      </BrowserRouter>
    );

    expect(await screen.findByText('Launch Day')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    await user.clear(screen.getByLabelText('Label'));
    await user.type(screen.getByLabelText('Label'), 'Launch Day Updated');
    await user.click(screen.getByRole('button', { name: 'Update period' }));

    await waitFor(() => {
      expect(vi.mocked(http.patch)).toHaveBeenCalledWith(
        'admin/archive/periods/launch-day',
        expect.objectContaining({
          json: expect.objectContaining({ label: 'Launch Day Updated' }),
        })
      );
      expect(vi.mocked(http.patch)).toHaveBeenCalledWith(
        'admin/archive/periods/launch-day',
        expect.objectContaining({
          json: expect.objectContaining({ recurring_month: null, recurring_day: null }),
        })
      );
    });

    await waitFor(() => expect(screen.getByText('Launch Day Updated')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Recalculate' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith('admin/archive/periods/launch-day/refresh');
    });

    await user.click(screen.getByRole('button', { name: 'Hide' }));

    await waitFor(() => {
      expect(vi.mocked(http.patch)).toHaveBeenCalledWith(
        'admin/archive/periods/launch-day',
        expect.objectContaining({ json: { status: 'hidden' } })
      );
    });
  });

  it('seeds curated periods', async () => {
    vi.mocked(http.get).mockImplementation(() => mockJsonResponse({ items: [basePeriod] }) as never);
    vi.mocked(http.post).mockImplementation((url: any) => {
      if (url === 'admin/archive/periods/seed') {
        return mockJsonResponse({ created: 4, skipped: 2 }) as never;
      }
      return mockJsonResponse(basePeriod) as never;
    });

    render(
      <BrowserRouter>
        <AdminArchivePeriods />
      </BrowserRouter>
    );

    expect(await screen.findByText('Launch Day')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Seed curated periods' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith('admin/archive/periods/seed');
    });

    expect(screen.getByText(/Seeded curated periods/)).toBeInTheDocument();
  });
});
