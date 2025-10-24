export type UUID = string;

export interface SearchHit {
  id: number;
  video_id: UUID;
  start_ms: number;
  end_ms: number;
  snippet: string;
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

export interface TranscriptResponse {
  video_id: UUID;
  segments: Segment[];
}

export interface VideoInfo {
  id: UUID;
  youtube_id: string;
  title?: string | null;
  duration_seconds?: number | null;
}
