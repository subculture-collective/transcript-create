import { http } from './api';

export type CommunityPost = {
  id: string;
  author_id: string;
  author_name: string;
  parent_id: string | null;
  kind: 'update' | 'discussion' | 'reply';
  body: string;
  status: 'draft' | 'published' | 'hidden';
  video_id: string | null;
  video_title: string | null;
  start_ms: number | null;
  end_ms: number | null;
  pinned: boolean;
  created_at: string;
  updated_at: string;
};
export type PostPage = { items: CommunityPost[]; next_offset: number | null };
export type CommunityReport = {
  id: string;
  post_id: string;
  reason: string;
  body: string;
  post_status: string;
};
export type TimelinePage = {
  items: Array<
    | { kind: 'post'; at: string; post: CommunityPost }
    | { kind: 'archive'; at: string; video: { id: string; title: string | null } }
  >;
  next_offset: number | null;
};
export const community = {
  timeline: (offset = 0) =>
    http.get('community/timeline', { searchParams: { offset } }).json<TimelinePage>(),
  edit: (id: string, body: string, ifMatch: string) =>
    http
      .patch(`community/posts/${id}`, { json: { body, if_match: ifMatch } })
      .json<CommunityPost>(),
  posts: (offset = 0, parentId?: string) =>
    http
      .get('community/posts', {
        searchParams: { offset, ...(parentId ? { parent_id: parentId } : {}) },
      })
      .json<PostPage>(),
  hidden: (offset = 0) =>
    http.get('community/hidden', { searchParams: { offset } }).json<PostPage>(),
  mine: (offset = 0) => http.get('community/mine', { searchParams: { offset } }).json<PostPage>(),
  create: (payload: {
    kind: string;
    body: string;
    publish: boolean;
    parent_id?: string;
    video_id?: string;
    start_ms?: number;
    end_ms?: number;
  }) => http.post('community/posts', { json: payload }).json<CommunityPost>(),
  publish: (id: string) => http.post(`community/posts/${id}/publish`).json<CommunityPost>(),
  remove: (id: string) => http.delete(`community/posts/${id}`),
  report: (id: string, reason: string) =>
    http.post(`community/posts/${id}/report`, { json: { reason } }),
  moderate: (id: string, action: string, reason: string) =>
    http.post(`community/posts/${id}/moderate`, { json: { action, reason } }).json<CommunityPost>(),
  reports: (offset = 0) =>
    http
      .get('community/reports', { searchParams: { offset } })
      .json<{ items: CommunityReport[]; next_offset: number | null }>(),
  resolve: (id: string, reason: string) =>
    http.post(`community/reports/${id}/resolve`, { json: { reason } }),
  export: async () => {
    const items: CommunityPost[] = [];
    let offset: number | null = 0;
    while (offset !== null) {
      const page: PostPage = await http
        .get('community/export', { searchParams: { offset } })
        .json<PostPage>();
      items.push(...page.items);
      offset = page.next_offset;
    }
    return { format: 'recollect-community-v1', exported_at: new Date().toISOString(), items };
  },
};
