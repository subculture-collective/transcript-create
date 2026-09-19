import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ClipExportControls from '../components/video/ClipExportControls';
import { http } from '../services/api';
vi.mock('../services', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
beforeEach(() => vi.restoreAllMocks());
it('requests the selected range and only offers download when complete', async () => {
  vi.spyOn(http, 'post').mockReturnValue({
    json: async () => ({ id: 'export', status: 'queued', expires_at: 1900000000 }),
  } as never);
  vi.spyOn(http, 'get').mockReturnValue({
    json: async () => ({ id: 'export', status: 'completed', expires_at: 1900000000 }),
  } as never);
  render(<ClipExportControls videoId="video" range={{ startMs: 1500, endMs: 3000 }} />);
  fireEvent.click(screen.getByRole('button', { name: 'Request selected clip' }));
  await waitFor(() =>
    expect(http.post).toHaveBeenCalledWith('clips', {
      json: { video_id: 'video', start_ms: 1500, end_ms: 3000 },
    })
  );
  expect(screen.queryByRole('link', { name: 'Download private MP4' })).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: 'Check export status' }));
  expect(await screen.findByRole('link', { name: 'Download private MP4' })).toHaveAttribute(
    'href',
    '/api/clips/export/download'
  );
});
it('blocks oversized selections and reports missing authorization', async () => {
  vi.spyOn(http, 'post').mockReturnValue({
    json: async () => {
      throw new Error('not authorized');
    },
  } as never);
  const view = render(<ClipExportControls videoId="video" range={{ startMs: 0, endMs: 120001 }} />);
  expect(screen.getByRole('button', { name: 'Request selected clip' })).toBeDisabled();
  view.rerender(<ClipExportControls videoId="video" range={{ startMs: 0, endMs: 1000 }} />);
  fireEvent.click(screen.getByRole('button', { name: 'Request selected clip' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('authorized, registered original');
});
