import ky from 'ky';
import type {
  ArchiveSearchFilters,
  ArchiveSummary,
  ExploreIntelligenceResponse,
  GroupedSearchResponse,
  MentionMapResponse,
  PaginatedVideos,
  SavedSearch,
  SavedSearchFilters,
  SearchResponse,
  StreamLibraryFilters,
  TimelineBucket,
  TimelineResponse,
  TranscriptResponse,
  VideoInfo,
} from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export const http = ky.create({ prefixUrl: API_BASE, timeout: 15000 });

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
  async search(q: string, opts?: ArchiveSearchFilters) {
    const params = new URLSearchParams({ q });
    appendSearchFilters(params, opts);
    return http.get('search', { searchParams: params }).json<SearchResponse>();
  },
  async searchGrouped(q: string, opts?: ArchiveSearchFilters) {
    const params = new URLSearchParams({ q });
    appendSearchFilters(params, opts);
    return http.get('search/grouped', { searchParams: params }).json<GroupedSearchResponse>();
  },
  async getMentionMap(q: string, opts?: ArchiveSearchFilters) {
    const params = new URLSearchParams({ q });
    appendSearchFilters(params, opts);
    return http.get('search/mention-map', { searchParams: params }).json<MentionMapResponse>();
  },
  async getArchiveSummary() {
    return http.get('archive/summary').json<ArchiveSummary>();
  },
  async getTimeline() {
    const response = await http.get('archive/timeline').json<TimelineResponse | TimelineBucket[]>();
    return normalizeTimelineResponse(response);
  },
  async getExploreIntelligence() {
    return http.get('archive/intelligence').json<ExploreIntelligenceResponse>();
  },
  async getTranscript(videoId: string) {
    return http
      .get(`videos/${videoId}/transcript`, { searchParams: { mode: 'formatted', source: 'best' } })
      .json<TranscriptResponse>();
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
    if (filters.completed_only !== undefined) searchParams.completed_only = String(filters.completed_only);
    if (filters.q) searchParams.q = filters.q;
    if (filters.date_field) searchParams.date_field = filters.date_field;
    if (filters.date_from) searchParams.date_from = filters.date_from;
    if (filters.date_to) searchParams.date_to = filters.date_to;
    if (filters.category) searchParams.category = filters.category;
    const response = await http.get('videos', { searchParams }).json<PaginatedVideos | VideoInfo[]>();
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

export async function apiCreateSavedSearch(payload: { query: string; filters?: SavedSearchFilters }) {
  return http.post('users/me/saved-searches', { json: payload }).json<SavedSearch>();
}

export async function apiDeleteSavedSearch(id: string) {
  return http.delete(`users/me/saved-searches/${id}`).json<{ ok: boolean }>();
}
