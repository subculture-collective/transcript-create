export type UUID = string;

export interface SearchHit {
  id: number;
  video_id: UUID;
  start_ms: number;
  end_ms: number;
  snippet: string;
  source?: 'whisper' | 'youtube' | 'merged';
}

export interface SearchResponse {
  total?: number;
  hits: SearchHit[];
}

export interface Segment {
  start_ms: number;
  end_ms: number;
  text: string;
  speaker_label?: string | null;
}

export interface TranscriptBlock {
  block_index: number;
  start_ms: number;
  end_ms: number;
  speaker_label?: string | null;
  text: string;
  segment_ids: number[];
  kind: 'paragraph' | 'speaker_turn';
  primary_source?: 'whisper' | 'youtube' | 'merged' | null;
  supporting_sources?: Array<'whisper' | 'youtube'>;
  needs_review?: boolean;
  merge_reason?: string | null;
  similarity?: number | null;
}

export interface TranscriptResponse {
  video_id: UUID;
  segments: Segment[];
  blocks?: TranscriptBlock[];
  source?: 'whisper' | 'youtube' | 'merged';
  source_label?: string;
}

export interface VideoInfo {
  id: UUID;
  youtube_id: string;
  title?: string | null;
  duration_seconds?: number | null;
  state?: string | null;
  caption_ingest_state?: string | null;
  diarization_state?: string | null;
  uploaded_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  channel_name?: string | null;
  language?: string | null;
  category?: string | null;
  has_whisper_transcript?: boolean;
  has_youtube_transcript?: boolean;
}

export type RecentVideo = VideoInfo;

export interface PageInfo {
  has_next_page: boolean;
  has_previous_page: boolean;
  next_cursor?: string | null;
  previous_cursor?: string | null;
  total_count?: number | null;
}

export interface PaginatedVideos {
  items: VideoInfo[];
  page_info: PageInfo;
}

export interface StreamLibraryFilters {
  limit?: number;
  offset?: number;
  completed_only?: boolean;
  q?: string;
  date_field?: 'uploaded_at' | 'created_at' | 'updated_at';
  date_from?: string;
  date_to?: string;
}
