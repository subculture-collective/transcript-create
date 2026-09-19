import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ATComposer from '../routes/ATComposer';
import { initializeAT, publishAT } from '../services/atproto';
const revoke = vi.hoisted(() => vi.fn());
vi.mock('../services/atproto', () => ({
  initializeAT: vi.fn(),
  onATInvalidated: () => () => {},
  checkedPassage: () => undefined,
  createPublicRecord: (text: string) => ({
    $type: 'app.bsky.feed.post',
    text,
    createdAt: '2026-09-19T00:00:00Z',
  }),
  publishAT: vi.fn(),
}));
beforeEach(() => {
  vi.clearAllMocks();
  window.location.hash = '';
  window.location.search = '';
  vi.mocked(initializeAT).mockResolvedValue({
    session: { sub: 'did:plc:example' },
    client: { revoke },
    resolver: 'https://bsky.social',
  } as never);
});
describe('explicit AT publishing', () => {
  it('requires destination consent and does not publish during restore', async () => {
    vi.mocked(publishAT).mockResolvedValue('at://did:plc:example/app.bsky.feed.post/example');
    render(<ATComposer />);
    await screen.findByText('did:plc:example');
    expect(publishAT).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'A public post' } });
    const button = screen.getByRole('button', { name: 'Publish to Bluesky publicly' });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(button);
    await screen.findByRole('link', { name: 'View on Bluesky' });
    expect(publishAT).toHaveBeenCalledTimes(1);
  });
  it('reuses an ambiguous attempt instead of creating a duplicate and preserves text', async () => {
    vi.mocked(publishAT).mockRejectedValue(new Error('timeout'));
    render(<ATComposer />);
    await screen.findByText('did:plc:example');
    fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Preserved post' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Publish to Bluesky publicly' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Post text')).toHaveValue('Preserved post');
    const firstKey = vi.mocked(publishAT).mock.calls[0][2];
    fireEvent.click(screen.getByRole('button', { name: 'Publish to Bluesky publicly' }));
    await waitFor(() => expect(publishAT).toHaveBeenCalledTimes(2));
    expect(vi.mocked(publishAT).mock.calls[1][2]).toBe(firstKey);
  });
});
