import ky from 'ky';
import type {
  ArchiveSearchFilters,
  AccountResponse,
  ActiveSession,
  AdminUser,
  LinkProviderResponse,
  LinkedIdentity,
  OAuthProvider,
  ProfileResponse,
  UserRole,
  ArchivePeriodOptionsResponse,
  ArchiveSummary,
  ExploreIntelligenceQuery,
  ExploreIntelligenceResponse,
  GroupedSearchResponse,
  MentionMapResponse,
  MentionCollectionResponse,
  PaginatedVideos,
  SavedSearch,
  SavedSearchFilters,
  SearchResponse,
  SearchSuggestionsResponse,
  StreamLibraryFilters,
  TimelineBucket,
  TimelineResponse,
  TopicTimelineResponse,
  OpinionHistoryResponse,
  RelatedEpisodesResponse,
  QuotedMomentsResponse,
  TranscriptResponse,
  VideoInfo,
  VideoChaptersResponse,
} from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function buildApiUrl(
  path = '',
  searchParams?: URLSearchParams | Record<string, string | number | boolean | null | undefined>,
  base = API_BASE
) {
  const normalizedBase = base.replace(/\/+$/, '');
  const normalizedPath = path.replace(/^\/+/, '');
  const url = normalizedPath
    ? `${normalizedBase ? `${normalizedBase}/` : '/'}${normalizedPath}`
    : normalizedBase || '/';

  if (!searchParams) return url;

  const params = searchParams instanceof URLSearchParams ? searchParams : new URLSearchParams();
  if (!(searchParams instanceof URLSearchParams)) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value == null) continue;
      params.set(key, String(value));
    }
  }

  const query = params.toString();
  return query ? `${url}?${query}` : url;
}

export const http = ky.create({
  prefixUrl: API_BASE,
  timeout: 15000,
  credentials: 'include',
  hooks: {
    beforeRequest: [
      ({ method, headers }) => {
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase()) && csrfToken) {
          headers.set('X-CSRF-Token', csrfToken);
        }
      },
    ],
  },
});

function appendSearchFilters(params: URLSearchParams, opts?: ArchiveSearchFilters) {
  if (!opts) return;
  if (opts.source) params.set('source', opts.source);
  if (opts.category) params.set('category', opts.category);
  if (opts.video_id) params.set('video_id', opts.video_id);
  if (opts.limit != null) params.set('limit', String(opts.limit));
  if (opts.offset != null) params.set('offset', String(opts.offset));
  if (opts.date_from) params.set('date_from', opts.date_from);
  if (opts.date_to) params.set('date_to', opts.date_to);
  if (opts.min_duration != null) params.set('min_duration', String(opts.min_duration));
  if (opts.max_duration != null) params.set('max_duration', String(opts.max_duration));
  if (opts.sort_by) params.set('sort_by', opts.sort_by);
}

function normalizeVideosResponse(response: PaginatedVideos | VideoInfo[]): PaginatedVideos {
  if (Array.isArray(response)) {
    return {
      items: response,
      page_info: {
        has_next_page: false,
        has_previous_page: false,
        next_cursor: null,
        previous_cursor: null,
        total_count: response.length,
      },
    };
  }

  return {
    items: response.items ?? [],
    page_info: response.page_info ?? {
      has_next_page: false,
      has_previous_page: false,
      next_cursor: null,
      previous_cursor: null,
      total_count: response.items?.length ?? 0,
    },
  };
}

function normalizeTimelineResponse(
  response:
    | TimelineResponse
    | TimelineBucket[]
    | { buckets?: TimelineBucket[]; items?: TimelineBucket[] }
) {
  if (Array.isArray(response)) return response;
  return response.buckets ?? response.items ?? [];
}

export const api = {
  async getAccount() {
    return http.get('account').json<AccountResponse>();
  },
  async updateProfile(payload: { name: string; avatar_url: string | null }) {
    return http.patch('account', { json: payload }).json<ProfileResponse>();
  },
  async listIdentities() {
    return http.get('account/identities').json<{ identities: LinkedIdentity[] }>();
  },
  async linkProvider(provider: OAuthProvider) {
    return http.post(`account/identities/${provider}/link`).json<LinkProviderResponse>();
  },
  async mergeProvider(provider: OAuthProvider) {
    return http.post(`account/identities/${provider}/merge`).json<LinkProviderResponse>();
  },
  async unlinkProvider(provider: OAuthProvider) {
    return http.delete(`account/identities/${provider}`).json<{ ok: boolean }>();
  },
  async listSessions() {
    return http.get('account/sessions').json<{ sessions: ActiveSession[] }>();
  },
  async revokeSession(sessionId: string) {
    return http.delete(`account/sessions/${encodeURIComponent(sessionId)}`).json<{ ok: boolean }>();
  },
  async revokeSessions(keepCurrent: boolean) {
    return http
      .delete('account/sessions', { searchParams: { keep_current: String(keepCurrent) } })
      .json<{ revoked: number }>();
  },
  async deleteAccount() {
    return http
      .delete('account', { json: { confirmation: 'DELETE' } })
      .json<{ deleted: boolean }>();
  },
  async listAdminUsers(query?: string, signal?: AbortSignal) {
    const searchParams = query ? { q: query } : undefined;
    return http.get('admin/users', { searchParams, signal }).json<{ items: AdminUser[] }>();
  },
  async updateAdminUserRole(userId: string, role: UserRole) {
    return http
      .put(`admin/users/${encodeURIComponent(userId)}/role`, { json: { role } })
      .json<{ user_id: string; role: UserRole }>();
  },
  async search(q: string, opts?: ArchiveSearchFilters, signal?: AbortSignal) {
    const params = new URLSearchParams({ q });
    appendSearchFilters(params, opts);
    return http.get('search', { searchParams: params, signal }).json<SearchResponse>();
  },
  async searchGrouped(q: string, opts?: ArchiveSearchFilters, signal?: AbortSignal) {
    const params = new URLSearchParams({ q });
    appendSearchFilters(params, opts);
    return http
      .get('search/grouped', { searchParams: params, signal })
      .json<GroupedSearchResponse>();
  },
  async getMentionMap(q: string, opts?: ArchiveSearchFilters) {
    const params = new URLSearchParams({ q });
    appendSearchFilters(params, opts);
    return http.get('search/mention-map', { searchParams: params }).json<MentionMapResponse>();
  },
  async getMentionCollection(q: string, opts?: ArchiveSearchFilters) {
    const params = new URLSearchParams({ q, format: 'json' });
    appendSearchFilters(params, opts);
    params.delete('offset');
    params.set('limit', '5000');
    return http
      .get('search/mentions/export', { searchParams: params })
      .json<MentionCollectionResponse>();
  },
  async getSearchSuggestions(q: string, limit = 10, signal?: AbortSignal) {
    const searchParams = new URLSearchParams({ q, limit: String(limit) });
    return http
      .get('search/suggestions', { searchParams, signal })
      .json<SearchSuggestionsResponse>();
  },
  async getArchiveSummary() {
    return http.get('archive/summary').json<ArchiveSummary>();
  },
  async getTimeline() {
    const response = await http.get('archive/timeline').json<TimelineResponse | TimelineBucket[]>();
    return normalizeTimelineResponse(response);
  },
  async getTopicTimeline(
    slug: string,
    opts?: { granularity?: 'week' | 'month'; date_from?: string; date_to?: string },
    signal?: AbortSignal
  ) {
    return http
      .get(`archive/topics/${encodeURIComponent(slug)}/timeline`, { searchParams: opts, signal })
      .json<TopicTimelineResponse>();
  },
  async getTopicOpinions(slug: string, signal?: AbortSignal) {
    return http
      .get(`archive/topics/${encodeURIComponent(slug)}/opinions`, { signal })
      .json<OpinionHistoryResponse>();
  },
  async correctOpinion(id: string, payload: { stance?: string; summary?: string; reason: string }) {
    return http
      .post(`admin/archive/opinions/${id}/correct`, { json: payload })
      .json<OpinionHistoryResponse>();
  },
  async retractOpinion(id: string, reason: string) {
    return http
      .post(`admin/archive/opinions/${id}/retract`, { json: { reason } })
      .json<OpinionHistoryResponse>();
  },
  async getRelatedEpisodes(videoId: string, signal?: AbortSignal) {
    return http.get(`videos/${videoId}/related`, { signal }).json<RelatedEpisodesResponse>();
  },
  async getQuotedMoments(videoId: string, signal?: AbortSignal) {
    return http.get(`videos/${videoId}/quoted-moments`, { signal }).json<QuotedMomentsResponse>();
  },
  async getExploreIntelligence(opts?: ExploreIntelligenceQuery) {
    const params = new URLSearchParams();
    if (opts?.period) params.set('period', opts.period);
    if (opts?.topic_limit != null) params.set('topic_limit', String(opts.topic_limit));
    if (opts?.granularity) params.set('granularity', opts.granularity);
    if (opts?.period_limit != null) params.set('period_limit', String(opts.period_limit));
    if (opts?.date_from) params.set('date_from', opts.date_from);
    if (opts?.date_to) params.set('date_to', opts.date_to);

    if (params.toString()) {
      return http
        .get('archive/intelligence', { searchParams: params })
        .json<ExploreIntelligenceResponse>();
    }

    return http.get('archive/intelligence').json<ExploreIntelligenceResponse>();
  },
  async getExplorePeriods(opts?: { kind?: string; limit?: number }) {
    const params = new URLSearchParams();
    if (opts?.kind) params.set('kind', opts.kind);
    if (opts?.limit != null) params.set('limit', String(opts.limit));

    if (params.toString()) {
      return http
        .get('archive/intelligence/periods', { searchParams: params })
        .json<ArchivePeriodOptionsResponse>();
    }

    return http.get('archive/intelligence/periods').json<ArchivePeriodOptionsResponse>();
  },
  async getTranscript(videoId: string, source: 'best' | 'whisper' | 'youtube' = 'best') {
    return http
      .get(`videos/${videoId}/transcript`, {
        searchParams: { mode: 'formatted', source },
        timeout: 60_000,
      })
      .json<TranscriptResponse>();
  },
  async getVideoChapters(videoId: string) {
    return http.get(`videos/${videoId}/chapters`).json<VideoChaptersResponse>();
  },
  async getVideo(videoId: string) {
    return http.get(`videos/${videoId}`).json<VideoInfo>();
  },
  async listRecentVideos(limit = 12) {
    const response = await http
      .get('videos', { searchParams: { completed_only: 'true', limit: String(limit) } })
      .json<PaginatedVideos | VideoInfo[]>();
    return normalizeVideosResponse(response).items;
  },
  async listStreamLibrary(filters: StreamLibraryFilters = {}) {
    const searchParams: Record<string, string> = {
      limit: String(filters.limit ?? 24),
      offset: String(filters.offset ?? 0),
    };
    if (filters.completed_only !== undefined)
      searchParams.completed_only = String(filters.completed_only);
    if (filters.q) searchParams.q = filters.q;
    if (filters.date_field) searchParams.date_field = filters.date_field;
    if (filters.date_from) searchParams.date_from = filters.date_from;
    if (filters.date_to) searchParams.date_to = filters.date_to;
    if (filters.category) searchParams.category = filters.category;
    const response = await http
      .get('videos', { searchParams })
      .json<PaginatedVideos | VideoInfo[]>();
    return normalizeVideosResponse(response);
  },
};

export async function apiListFavorites(videoId?: string) {
  const searchParams = videoId ? new URLSearchParams({ video_id: videoId }) : undefined;
  return http.get('users/me/favorites', { searchParams }).json<{
    items: Array<{
      id: string;
      video_id: string;
      start_ms: number;
      end_ms: number;
      text?: string;
    }>;
  }>();
}

export async function apiAddFavorite(payload: {
  video_id: string;
  start_ms: number;
  end_ms: number;
  text?: string;
}) {
  return http.post('users/me/favorites', { json: payload }).json<{ id: string }>();
}

export async function apiDeleteFavorite(id: string) {
  return http.delete(`users/me/favorites/${id}`).json<{ ok: boolean }>();
}

export async function apiListSavedSearches() {
  return http.get('users/me/saved-searches').json<{ items: SavedSearch[] }>();
}

export async function apiCreateSavedSearch(payload: {
  query: string;
  filters?: SavedSearchFilters;
}) {
  return http.post('users/me/saved-searches', { json: payload }).json<SavedSearch>();
}

export async function apiDeleteSavedSearch(id: string) {
  return http.delete(`users/me/saved-searches/${id}`).json<{ ok: boolean }>();
}
