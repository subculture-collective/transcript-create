import ky from 'ky';
import type { PaginatedVideos, SearchResponse, StreamLibraryFilters, TranscriptResponse, VideoInfo } from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export const http = ky.create({ prefixUrl: API_BASE, timeout: 15000 });

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

export const api = {
  async search(
    q: string,
    opts?: { source?: 'best' | 'native' | 'youtube'; video_id?: string; limit?: number; offset?: number }
  ) {
    const params = new URLSearchParams({ q });
    if (opts?.source) params.set('source', opts.source);
    if (opts?.video_id) params.set('video_id', opts.video_id);
    if (opts?.limit) params.set('limit', String(opts.limit));
    if (opts?.offset) params.set('offset', String(opts.offset));
    return http.get('search', { searchParams: params }).json<SearchResponse>();
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
