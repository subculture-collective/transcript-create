import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CommunityPage from '../routes/CommunityPage';
import { community, type CommunityPost } from '../services/community';

const state = vi.hoisted(() => ({
  enabled: true,
  role: 'admin',
  user: { id: 'creator' } as { id: string } | null,
}));
vi.mock('../services/site', () => ({
  useSite: () => ({ community_enabled: state.enabled, creator_name: 'Demo' }),
}));
vi.mock('../services', () => ({ useAuth: () => ({ user: state.user, role: state.role }) }));
vi.mock('../services/community', () => ({
  community: {
    posts: vi.fn(),
    mine: vi.fn(),
    create: vi.fn(),
    publish: vi.fn(),
    remove: vi.fn(),
    reports: vi.fn(),
    export: vi.fn(),
  },
}));
const post: CommunityPost = {
  id: 'root',
  author_id: 'creator',
  author_name: 'Creator',
  parent_id: null,
  kind: 'update',
  body: 'Welcome',
  status: 'published',
  video_id: null,
  video_title: null,
  start_ms: null,
  end_ms: null,
  pinned: false,
  created_at: '2026-09-19T12:00:00Z',
  updated_at: '2026-09-19T12:00:00Z',
};
const mount = (path = '/community') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <CommunityPage />
    </MemoryRouter>
  );
beforeEach(() => {
  vi.resetAllMocks();
  state.enabled = true;
  state.role = 'admin';
  state.user = { id: 'creator' };
  vi.mocked(community.posts).mockResolvedValue({ items: [], next_offset: null });
  vi.mocked(community.mine).mockResolvedValue({ items: [], next_offset: null });
});
describe('community publishing', () => {
  it('keeps drafts private until explicitly published', async () => {
    vi.mocked(community.create).mockResolvedValue({ ...post, status: 'draft' });
    mount();
    await screen.findByText('No public posts yet. Conversations begin with a passage.');
    fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Draft news' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() =>
      expect(community.create).toHaveBeenCalledWith({
        kind: 'update',
        body: 'Draft news',
        publish: false,
      })
    );
    expect(await screen.findByText('Draft saved. Find it under My posts.')).toBeInTheDocument();
  });
  it('preserves text when publishing fails', async () => {
    vi.mocked(community.create).mockRejectedValue(new Error('offline'));
    mount();
    fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Keep this text' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish publicly' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Post text')).toHaveValue('Keep this text');
  });
  it('opens replies without losing them when the feed refreshes', async () => {
    vi.mocked(community.posts).mockImplementation(async (_offset, parent) => ({
      items: parent
        ? [{ ...post, id: 'reply', parent_id: 'root', kind: 'reply', body: 'In context' }]
        : [post],
      next_offset: null,
    }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Open discussion' }));
    expect(await screen.findByText('In context')).toBeInTheDocument();
    expect(screen.getByLabelText('Reply publicly')).toBeInTheDocument();
  });
  it('carries the exact selected source range into a member discussion', async () => {
    state.role = 'user';
    mount('/community?video_id=00000000-0000-0000-0000-000000000902&start_ms=1000&end_ms=4500');
    fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Discuss context' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish publicly' }));
    await waitFor(() =>
      expect(community.create).toHaveBeenCalledWith({
        kind: 'discussion',
        body: 'Discuss context',
        publish: true,
        video_id: '00000000-0000-0000-0000-000000000902',
        start_ms: 1000,
        end_ms: 4500,
      })
    );
  });
  it('does not expose publishing when disabled or anonymous', () => {
    state.enabled = false;
    mount();
    expect(screen.queryByLabelText('Post text')).not.toBeInTheDocument();
    expect(community.posts).not.toHaveBeenCalled();
  });
});
