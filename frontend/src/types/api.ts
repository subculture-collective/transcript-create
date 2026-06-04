export type UUID = string;

export interface SearchHit {
  id: number;
  video_id: UUID;
  start_ms: number;
  end_ms: number;
  snippet: string;
  source?: 'whisper' | 'youtube' | 'merged';
}

export interface SearchMoment {
  id: number;
  video_id: UUID;
  start_ms: number;
  end_ms: number;
  snippet: string;
  source?: 'whisper' | 'youtube' | 'merged';
}

export interface EpisodeSearchGroup {
  video: VideoInfo;
  moments: SearchMoment[];
}

export interface GroupedSearchResponse {
  total_moments: number;
  total_videos: number;
  groups: EpisodeSearchGroup[];
  query_time_ms?: number | null;
}

export interface MentionMapResponse {
  query: string;
  total_moments: number;
  total_videos: number;
  first_mentioned_year?: number | null;
  most_discussed_period?: string | null;
  most_discussed_count?: number;
  recent_mentions_90d?: number;
  related_topics?: string[];
  top_episodes_count?: number;
  first_mention?: (SearchMoment & { video?: VideoInfo | null }) | null;
  latest_mention?: (SearchMoment & { video?: VideoInfo | null }) | null;
  top_episodes: EpisodeSearchGroup[];
  query_time_ms?: number | null;
}

export interface ArchivePopularSearch {
  term: string;
  frequency: number;
}

export interface ArchiveSummary {
  creator_name: string;
  video_count: number;
  total_duration_seconds: number;
  transcript_word_count: number;
  updated_at?: string | null;
  recent_videos: VideoInfo[];
  popular_searches: ArchivePopularSearch[];
}

export interface ArchiveEvidenceMoment {
  video: VideoInfo;
  start_ms: number;
  end_ms: number;
  snippet: string;
  topic?: string | null;
}

export interface ArchiveTopicCard {
  slug: string;
  label: string;
  kind?: 'topic' | 'series' | 'category' | 'person' | string | null;
  source: 'curated' | 'automatic' | 'hybrid' | string;
  status?: 'published' | 'hidden' | 'candidate' | string;
  is_editable?: boolean;
  aliases: string[];
  total_moments: number;
  total_videos: number;
  recent_mentions_90d: number;
  trend_score: number;
  related_topics: string[];
  evidence: ArchiveEvidenceMoment[];
}

export interface ArchiveTrendingSearch {
  term: string;
  frequency: number;
  trend_score: number;
  source: 'search' | 'transcript' | 'hybrid' | string;
}

export interface ArchivePeriodIntelligence {
  period: string;
  label: string;
  video_count: number;
  total_duration_seconds: number;
  videos: VideoInfo[];
  top_topics: ArchiveTopicCard[];
  summary: string;
  evidence: ArchiveEvidenceMoment[];
}

export interface ArchivePeriodOption {
  slug: string;
  label: string;
  kind: string;
  date_from: string;
  date_to: string;
  description?: string | null;
  recurring_month?: number | null;
  recurring_day?: number | null;
  video_count: number;
  total_duration_seconds: number;
}

export interface ArchiveNamedPeriodAdminResponse {
  id: string | number;
  slug: string;
  label: string;
  kind: string;
  date_from: string;
  date_to: string;
  description?: string | null;
  status: 'published' | 'hidden' | string;
  sort_order?: number | null;
  recurring_month?: number | null;
  recurring_day?: number | null;
  video_count: number;
  total_duration_seconds: number;
  summary?: string | null;
  calculated_at?: string | null;
}

export interface ArchiveNamedPeriodUpsertPayload {
  label: string;
  slug?: string;
  kind: string;
  date_from: string;
  date_to: string;
  description?: string | null;
  status: 'published' | 'hidden';
  sort_order?: number | null;
  recurring_month?: number | null;
  recurring_day?: number | null;
}

export interface ArchivePerson {
  slug: string;
  display_name: string;
  aliases: string[];
  description?: string | null;
  role?: string | null;
}

export interface ArchiveVideoTag {
  slug: string;
  label: string;
  kind: string;
  description?: string | null;
}

export interface ArchivePersonAdminResponse extends ArchivePerson {
  id: UUID;
  status: 'published' | 'hidden' | string;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ArchiveVideoTagAdminResponse extends ArchiveVideoTag {
  id: UUID;
  status: 'published' | 'hidden' | string;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ArchivePersonUpsertPayload {
  slug?: string;
  display_name: string;
  aliases: string[];
  description?: string | null;
  status: 'published' | 'hidden';
  sort_order?: number | null;
}

export interface ArchiveVideoTagUpsertPayload {
  slug?: string;
  label: string;
  kind: string;
  description?: string | null;
  status: 'published' | 'hidden';
  sort_order?: number | null;
}

export interface ArchiveVideoAssignmentPayload {
  people: Array<{ slug: string; role?: string }>;
  tags: Array<{ slug: string }>;
}

export interface ArchiveVideoMetadataItem extends VideoInfo {
  people: ArchivePerson[];
  tags: ArchiveVideoTag[];
}

export interface ArchiveVideoMetadataListResponse {
  items: ArchiveVideoMetadataItem[];
  total?: number | null;
  query_time_ms?: number | null;
}

export interface ArchiveLabelResponse {
  id: UUID;
  slug: string;
  label: string;
  kind: string;
  status: string;
  source: string;
  publish_tier: string;
  confidence_score: number;
  description?: string | null;
}

export interface ArchiveLabelListResponse {
  items: ArchiveLabelResponse[];
}

export interface ArchiveLabelAssignmentResponse {
  id: UUID;
  label: ArchiveLabelResponse;
  video_id: UUID;
  unit_type: string;
  start_ms?: number | null;
  end_ms?: number | null;
  status: string;
  publish_tier: string;
  confidence_score: number;
  evidence_count: number;
  evidence: Array<Record<string, unknown>>;
}

export interface ArchiveLabelAssignmentListResponse {
  items: ArchiveLabelAssignmentResponse[];
}

export interface ArchiveLabelReviewAction {
  action: 'approve' | 'reject' | 'publish' | 'hide' | 'merge' | 'rename';
  label?: string | null;
  target_label_id?: UUID | null;
  reason?: string | null;
}

export interface ArchiveLabelExtractionResponse {
  video_id: UUID;
  extraction_tier: string;
  run_id?: string | null;
  windows: number;
  candidates: number;
  assignments: number;
}

export interface ArchivePeriodOptionsResponse {
  periods: ArchivePeriodOption[];
  selected_period?: ArchivePeriodOption | null;
  query_time_ms?: number | null;
}

export interface ExploreIntelligenceResponse {
  summary: ArchiveSummary;
  exploration_modes: string[];
  trending_searches: ArchiveTrendingSearch[];
  suggested_searches: ArchiveTrendingSearch[];
  topic_cards: ArchiveTopicCard[];
  people?: ArchivePerson[];
  tags?: ArchiveVideoTag[];
  periods: ArchivePeriodIntelligence[];
  selected_period?: ArchivePeriodOption | null;
  period_options: ArchivePeriodOption[];
  query_time_ms?: number | null;
}

export interface ExploreIntelligenceQuery {
  period?: string;
  topic_limit?: number;
  granularity?: 'month' | 'week';
  period_limit?: number;
  date_from?: string;
  date_to?: string;
}

export interface TimelineBucket {
  period: string;
  label: string;
  video_count: number;
  total_duration_seconds: number;
  videos: VideoInfo[];
}

export interface TimelineResponse {
  buckets?: TimelineBucket[];
  items?: TimelineBucket[];
  query_time_ms?: number | null;
}

export interface SavedSearchFilters {
  source?: 'best' | 'native' | 'youtube';
  category?: string;
  date_from?: string;
  date_to?: string;
  min_duration?: number;
  max_duration?: number;
  sort_by?: string;
  video_id?: string;
  limit?: number;
  offset?: number;
}

export interface SavedSearch {
  id: UUID;
  query: string;
  filters: SavedSearchFilters;
  created_at?: string | null;
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
  people?: ArchivePerson[];
  tags?: ArchiveVideoTag[];
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
  category?: string;
}

export interface ArchiveSearchFilters {
  source?: 'best' | 'native' | 'youtube';
  category?: string;
  video_id?: string;
  limit?: number;
  offset?: number;
  date_from?: string;
  date_to?: string;
  min_duration?: number;
  max_duration?: number;
  sort_by?: string;
}
