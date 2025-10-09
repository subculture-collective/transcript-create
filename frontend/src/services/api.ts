import ky from 'ky'
import type { SearchResponse, TranscriptResponse, VideoInfo } from '../types/api'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export const http = ky.create({ prefixUrl: API_BASE, timeout: 15000 })

export const api = {
  async search(q: string, opts?: { source?: 'native' | 'youtube'; video_id?: string; limit?: number; offset?: number }) {
    const params = new URLSearchParams({ q })
    if (opts?.source) params.set('source', opts.source)
    if (opts?.video_id) params.set('video_id', opts.video_id)
    if (opts?.limit) params.set('limit', String(opts.limit))
    if (opts?.offset) params.set('offset', String(opts.offset))
    return http.get('search', { searchParams: params }).json<SearchResponse>()
  },
  async getTranscript(videoId: string) {
    return http.get(`videos/${videoId}/transcript`).json<TranscriptResponse>()
  },
  async getVideo(videoId: string) {
    return http.get(`videos/${videoId}`).json<VideoInfo>()
  },
}
