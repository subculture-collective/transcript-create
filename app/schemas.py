import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class QualitySettingsInput(BaseModel):
    """Quality settings for transcription."""

    preset: Literal["fast", "balanced", "accurate"] = Field(
        "balanced", description="Quality preset (fast/balanced/accurate)"
    )
    language: Optional[str] = Field(None, description="Language code (e.g., 'en', 'es', 'fr') or None for auto-detect")
    model: Optional[str] = Field(None, description="Whisper model (tiny/base/small/medium/large/large-v3)")
    beam_size: Optional[int] = Field(
        None, ge=1, le=10, description="Beam size for decoding (1-10, higher = more accurate)"
    )
    temperature: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Sampling temperature (0.0-1.0, 0.0 = greedy)"
    )
    word_timestamps: Optional[bool] = Field(True, description="Extract word-level timestamps")
    vad_filter: Optional[bool] = Field(None, description="Voice Activity Detection filter (faster-whisper only)")


class JobCreate(BaseModel):
    """Request body for creating a new transcription job."""

    url: HttpUrl = Field(
        ...,
        description="YouTube video or channel URL to transcribe",
        examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
    )
    kind: Literal["single", "channel"] = Field(
        "single",
        description="Type of job: 'single' for one video, 'channel' for all videos in a channel",
    )
    quality: Optional[QualitySettingsInput] = Field(None, description="Quality settings for transcription")
    vocabulary_ids: Optional[List[uuid.UUID]] = Field(
        None, description="Custom vocabulary IDs to apply during transcription"
    )
    batch_id: Optional[str] = Field(None, description="Optional batch identifier for coordinating multiple jobs")
    batch_expected_jobs: Optional[int] = Field(
        None, ge=1, description="Number of jobs expected in this batch before staged promotion is allowed"
    )
    staged: bool = Field(False, description="If true, ingest YouTube captions first, then queue native transcription")

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: HttpUrl) -> HttpUrl:
        """Validate that the URL is a YouTube URL."""
        url_str = str(v)
        youtube_patterns = [
            r"^https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
            r"^https?://(www\.)?youtube\.com/channel/[\w-]+",
            r"^https?://(www\.)?youtube\.com/@[\w-]+",
            r"^https?://youtu\.be/[\w-]+",
        ]
        if not any(re.match(pattern, url_str) for pattern in youtube_patterns):
            raise ValueError("URL must be a valid YouTube video or channel URL")
        return v


class JobStatus(BaseModel):
    """Status information for a transcription job."""

    id: uuid.UUID = Field(..., description="Unique identifier for the job")
    kind: str = Field(..., description="Job type: 'single' or 'channel'")
    state: str = Field(
        ...,
        description="Current state: 'pending', 'expanded', 'completed', 'failed'",
    )
    error: Optional[str] = Field(None, description="Error message if job failed")
    created_at: datetime = Field(..., description="Timestamp when job was created")
    updated_at: datetime = Field(..., description="Timestamp when job was last updated")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "kind": "single",
                "state": "completed",
                "error": None,
                "created_at": "2025-10-25T10:30:00Z",
                "updated_at": "2025-10-25T10:35:00Z",
            }
        }
    }


class Segment(BaseModel):
    """A single segment of transcribed text with timing information."""

    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    text: str = Field(..., description="Transcribed text content")
    speaker_label: Optional[str] = Field(None, description="Speaker label from diarization (e.g., 'Speaker 1')")

    model_config = {
        "json_schema_extra": {
            "example": {
                "start_ms": 1000,
                "end_ms": 3500,
                "text": "Hello and welcome to this video",
                "speaker_label": "Speaker 1",
            }
        }
    }


class TranscriptResponse(BaseModel):
    """Complete transcript for a video with all segments."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    segments: List[Segment] = Field(..., description="List of transcript segments in chronological order")
    source: Literal["whisper", "youtube", "merged"] = Field("whisper", description="Transcript source used for this response")
    source_label: str = Field("Whisper transcript", description="Human-readable transcript source label")

    model_config = {
        "json_schema_extra": {
            "example": {
                "video_id": "123e4567-e89b-12d3-a456-426614174000",
                "segments": [
                    {
                        "start_ms": 1000,
                        "end_ms": 3500,
                        "text": "Hello and welcome to this video",
                        "speaker_label": "Speaker 1",
                    }
                ],
            }
        }
    }


class YTSegment(BaseModel):
    """A segment from YouTube's native closed captions."""

    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    text: str = Field(..., description="Caption text content")


class YouTubeTranscriptResponse(BaseModel):
    """YouTube's native closed captions for a video."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    language: Optional[str] = Field(None, description="Language code of captions (e.g., 'en')")
    kind: Optional[str] = Field(None, description="Caption type: 'asr' (auto-generated) or manual")
    full_text: Optional[str] = Field(None, description="Full transcript text concatenated")
    segments: List[YTSegment] = Field(..., description="List of caption segments")
    blocks: List["TranscriptBlockResponse"] = Field(default_factory=list, description="Formatted caption blocks")
    source: Literal["youtube"] = Field("youtube", description="Transcript source used for this response")
    source_label: str = Field("YouTube captions", description="Human-readable transcript source label")


class SearchHit(BaseModel):
    """A single search result matching the query."""

    id: int = Field(..., description="Segment ID")
    video_id: uuid.UUID = Field(..., description="Video containing this segment")
    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    snippet: str = Field(..., description="Text snippet with search term highlighted")
    source: Literal["whisper", "youtube", "merged"] = Field("whisper", description="Transcript source containing this hit")
    video_title: Optional[str] = Field(None, description="Video title for progressive archive UIs")
    channel_name: Optional[str] = Field(None, description="Channel name for progressive archive UIs")
    uploaded_at: Optional[datetime] = Field(None, description="Video upload time")
    duration_seconds: Optional[int] = Field(None, description="Video duration in seconds")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": 12345,
                "video_id": "123e4567-e89b-12d3-a456-426614174000",
                "start_ms": 45000,
                "end_ms": 48500,
                "snippet": "This is an example of <em>search term</em> in context",
            }
        }
    }


class SearchResponse(BaseModel):
    """Search results from full-text search."""

    total: Optional[int] = Field(None, description="Total number of matching results (only with OpenSearch backend)")
    hits: List[SearchHit] = Field(..., description="List of search results")
    query_time_ms: Optional[int] = Field(None, description="Time taken to execute the query in milliseconds")


class ArchivePopularSearch(BaseModel):
    term: str = Field(..., description="Popular search term")
    frequency: int = Field(..., description="Search frequency")


class ArchiveSummaryStats(BaseModel):
    video_count: int = Field(0, description="Count of archived videos with transcript coverage")
    total_duration_seconds: int = Field(0, description="Total duration across archived videos")
    transcript_word_count: int = Field(0, description="Estimated transcript word count")
    archive_updated_at: Optional[datetime] = Field(None, description="Most recent archive update timestamp")


class ArchiveSummary(BaseModel):
    creator_name: str = Field("HasAnAra", description="Archive display name")
    video_count: int = Field(0, description="Count of archived videos with transcript coverage")
    total_duration_seconds: int = Field(0, description="Total duration across archived videos")
    transcript_word_count: int = Field(0, description="Estimated transcript word count")
    updated_at: Optional[datetime] = Field(None, description="Most recent archive update timestamp")
    recent_videos: List["VideoInfo"] = Field(default_factory=list, description="Most recent archived videos")
    popular_searches: List[ArchivePopularSearch] = Field(default_factory=list, description="Popular archive searches")


class SearchMoment(SearchHit):
    """A timestamped search result used in grouped archive views."""


class EpisodeSearchGroup(BaseModel):
    video: "VideoInfo" = Field(..., description="Video metadata for the group")
    moments: List[SearchMoment] = Field(default_factory=list, description="Moments matched in this video")


class GroupedSearchResponse(BaseModel):
    total_moments: int = Field(..., description="Total matched moments in the response window")
    total_videos: int = Field(..., description="Number of videos with at least one moment")
    groups: List[EpisodeSearchGroup] = Field(default_factory=list, description="Search groups by video")
    query_time_ms: Optional[int] = Field(None, description="Time taken to execute the query in milliseconds")


class MentionMap(BaseModel):
    query: str = Field(..., description="Original search query")
    total_moments: int = Field(..., description="Total matched moments in the response window")
    total_videos: int = Field(..., description="Number of videos with at least one mention")
    first_mentioned_year: Optional[int] = Field(None, description="Year of the earliest dated mention")
    most_discussed_period: Optional[str] = Field(None, description="Period with the most matched moments, usually a year")
    most_discussed_count: int = Field(0, description="Number of matched moments in the most discussed period")
    recent_mentions_90d: int = Field(0, description="Matched moments from the last 90 days")
    related_topics: List[str] = Field(default_factory=list, description="Citation-derived co-occurring terms from matched snippets")
    top_episodes_count: int = Field(0, description="Number of top episodes included in this mention map")
    first_mention: Optional[SearchMoment] = Field(None, description="Earliest matching mention")
    latest_mention: Optional[SearchMoment] = Field(None, description="Latest matching mention")
    top_episodes: List[EpisodeSearchGroup] = Field(default_factory=list, description="Top matching episodes")
    query_time_ms: Optional[int] = Field(None, description="Time taken to execute the query in milliseconds")


class TimelineBucket(BaseModel):
    period: str = Field(..., description="Bucket period label, e.g. 2026-05")
    label: str = Field(..., description="Human-readable bucket label")
    video_count: int = Field(..., description="Number of videos in the bucket")
    total_duration_seconds: int = Field(..., description="Total duration for videos in the bucket")
    videos: List["VideoInfo"] = Field(default_factory=list, description="Videos in chronological order")


class ArchiveTimelineResponse(BaseModel):
    buckets: List[TimelineBucket] = Field(default_factory=list, description="Chronological archive buckets")
    query_time_ms: Optional[int] = Field(None, description="Time taken to build the timeline")


class ArchiveEvidenceMoment(BaseModel):
    video: "VideoInfo" = Field(..., description="VOD containing the cited evidence")
    start_ms: int = Field(..., description="Moment start timestamp")
    end_ms: int = Field(..., description="Moment end timestamp")
    snippet: str = Field(..., description="Evidence snippet from transcript text")
    topic: Optional[str] = Field(None, description="Topic or query this evidence supports")


class ArchiveTopicCard(BaseModel):
    slug: str = Field(..., description="Stable topic slug")
    label: str = Field(..., description="Public topic label")
    source: str = Field(..., description="curated, automatic, or hybrid")
    status: str = Field("published", description="Public lifecycle status for the topic")
    is_editable: bool = Field(True, description="Whether operators may edit this topic")
    aliases: List[str] = Field(default_factory=list, description="Search aliases used for this topic")
    total_moments: int = Field(0, description="Matched transcript moments")
    total_videos: int = Field(0, description="VODs with at least one matched moment")
    recent_mentions_90d: int = Field(0, description="Mentions in the last 90 days")
    trend_score: float = Field(0, description="Combined search and transcript trend score")
    related_topics: List[str] = Field(default_factory=list, description="Related topic labels")
    evidence: List[ArchiveEvidenceMoment] = Field(default_factory=list, description="Timestamped evidence moments")


class ArchiveTrendingSearch(BaseModel):
    term: str = Field(..., description="Trending or popular public search term")
    frequency: int = Field(0, description="Search frequency from suggestion analytics")
    trend_score: float = Field(0, description="Combined search and transcript trend score")
    source: str = Field("search", description="search, transcript, or hybrid")


class ArchiveNamedPeriod(BaseModel):
    slug: str = Field(..., description="Stable period slug")
    label: str = Field(..., description="Public period label")
    kind: str = Field(..., description="month, week, event, or date")
    date_from: date = Field(..., description="Inclusive start date")
    date_to: date = Field(..., description="Inclusive end date")
    description: Optional[str] = Field(None, description="Optional period description")
    status: str = Field("published", description="Period lifecycle status")
    sort_order: int = Field(0, description="Ordering weight for UI presentation")
    video_count: int = Field(0, description="Cached video count for the period")
    total_duration_seconds: int = Field(0, description="Cached duration for the period")
    summary: str = Field("", description="Cached period summary")


class ArchivePeriodOption(BaseModel):
    slug: str = Field(..., description="Stable period slug")
    label: str = Field(..., description="Public period label")
    kind: str = Field(..., description="month, week, event, or date")
    date_from: date = Field(..., description="Inclusive start date")
    date_to: date = Field(..., description="Inclusive end date")
    description: Optional[str] = Field(None, description="Optional period description")
    video_count: int = Field(0, description="Cached video count for the period")
    total_duration_seconds: int = Field(0, description="Cached duration for the period")


class ArchivePeriodOptionsResponse(BaseModel):
    periods: List[ArchivePeriodOption] = Field(default_factory=list, description="Available predefined archive periods")
    selected_period: Optional[ArchivePeriodOption] = Field(None, description="Currently selected period")


class ArchivePeriodIntelligence(BaseModel):
    period: str = Field(..., description="Period identifier, e.g. 2026-05")
    label: str = Field(..., description="Human-readable period label")
    video_count: int = Field(..., description="VOD count in this period")
    total_duration_seconds: int = Field(..., description="Total VOD duration in this period")
    videos: List["VideoInfo"] = Field(default_factory=list, description="Representative VODs")
    top_topics: List[ArchiveTopicCard] = Field(default_factory=list, description="Top topics for the period")
    summary: str = Field(..., description="Extractive or generated period summary")
    evidence: List[ArchiveEvidenceMoment] = Field(default_factory=list, description="Citations supporting the summary")


class ArchiveIntelligenceResponse(BaseModel):
    summary: ArchiveSummary = Field(..., description="Archive summary stats and recent VODs")
    exploration_modes: List[str] = Field(default_factory=list, description="Available exploration modes")
    trending_searches: List[ArchiveTrendingSearch] = Field(default_factory=list, description="Trending public searches")
    suggested_searches: List[ArchiveTrendingSearch] = Field(default_factory=list, description="Suggested archive searches")
    topic_cards: List[ArchiveTopicCard] = Field(default_factory=list, description="Hybrid curated/automatic topic cards")
    periods: List[ArchivePeriodIntelligence] = Field(default_factory=list, description="Timeline periods enriched with topic/evidence data")
    selected_period: Optional[ArchivePeriodOption] = Field(None, description="Currently selected predefined period")
    period_options: List[ArchivePeriodOption] = Field(default_factory=list, description="Available predefined archive periods")
    query_time_ms: Optional[int] = Field(None, description="Time taken to compose archive intelligence")


class SavedSearchCreate(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Saved search query")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Serialized search filters")


class SavedSearch(BaseModel):
    id: uuid.UUID = Field(..., description="Saved search identifier")
    query: str = Field(..., description="Saved search query")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Serialized search filters")
    created_at: datetime = Field(..., description="When the search was saved")


class SavedSearchesResponse(BaseModel):
    items: List[SavedSearch] = Field(default_factory=list, description="Saved searches")


class SearchSuggestion(BaseModel):
    """A search suggestion for autocomplete."""

    term: str = Field(..., description="Suggested search term")
    frequency: int = Field(..., description="Number of times this term has been searched")


class SearchSuggestionsResponse(BaseModel):
    """Response containing search suggestions."""

    suggestions: List[SearchSuggestion] = Field(..., description="List of search suggestions")


class SearchHistoryItem(BaseModel):
    """A single search history entry."""

    query: str = Field(..., description="Search query text")
    filters: Optional[Dict[str, Any]] = Field(None, description="Filters applied with the search")
    result_count: Optional[int] = Field(None, description="Number of results returned")
    created_at: datetime = Field(..., description="When the search was performed")


class SearchHistoryResponse(BaseModel):
    """Response containing search history."""

    items: List[SearchHistoryItem] = Field(..., description="List of search history items")


class SearchAnalytics(BaseModel):
    """Search analytics summary."""

    popular_terms: List[Dict[str, Any]] = Field(..., description="Most popular search terms")
    zero_result_searches: List[Dict[str, Any]] = Field(..., description="Searches that returned no results")
    search_volume: List[Dict[str, Any]] = Field(..., description="Search volume over time")
    avg_results_per_query: Optional[float] = Field(None, description="Average number of results per query")
    total_searches: int = Field(..., description="Total number of searches")


class VideoInfo(BaseModel):
    """Basic information about a video."""

    id: uuid.UUID = Field(..., description="Unique identifier for the video")
    youtube_id: str = Field(..., description="YouTube video ID")
    title: Optional[str] = Field(None, description="Video title")
    duration_seconds: Optional[int] = Field(None, description="Video duration in seconds", ge=0)
    state: Optional[str] = Field(None, description="Processing state")
    caption_ingest_state: Optional[str] = Field(None, description="YouTube caption ingest state")
    diarization_state: Optional[str] = Field(None, description="Diarization state")
    uploaded_at: Optional[datetime] = Field(None, description="YouTube upload or stream publish time")
    created_at: Optional[datetime] = Field(None, description="Local row creation time")
    updated_at: Optional[datetime] = Field(None, description="Local row update time")
    channel_name: Optional[str] = Field(None, description="YouTube channel name")
    language: Optional[str] = Field(None, description="Detected or declared language")
    category: Optional[str] = Field(None, description="Video category")
    has_whisper_transcript: bool = Field(False, description="Whether Whisper transcript segments exist")
    has_youtube_transcript: bool = Field(False, description="Whether YouTube captions exist")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "youtube_id": "dQw4w9WgXcQ",
                "title": "Example Video Title",
                "duration_seconds": 212,
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error code identifying the error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details and context")

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": [{"field": "url", "message": "Invalid URL format"}]},
            }
        }
    }


class SearchQuery(BaseModel):
    """Query parameters for search endpoint."""

    q: str = Field(..., min_length=1, max_length=500, description="Search query")
    source: Literal["best", "native", "youtube"] = "best"
    video_id: Optional[uuid.UUID] = None
    limit: int = Field(50, ge=1, le=200, description="Number of results to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class PageInfo(BaseModel):
    """Pagination information for cursor-based pagination."""

    has_next_page: bool = Field(..., description="Whether there are more results available")
    has_previous_page: bool = Field(..., description="Whether there are previous results available")
    next_cursor: Optional[str] = Field(None, description="Cursor for fetching the next page")
    previous_cursor: Optional[str] = Field(None, description="Cursor for fetching the previous page")
    total_count: Optional[int] = Field(None, description="Total number of items (may be None for performance)")


class PaginatedVideos(BaseModel):
    """Paginated list of videos."""

    items: List[VideoInfo] = Field(..., description="List of videos in current page")
    page_info: PageInfo = Field(..., description="Pagination information")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "youtube_id": "dQw4w9WgXcQ",
                        "title": "Example Video",
                        "duration_seconds": 212,
                    }
                ],
                "page_info": {
                    "has_next_page": True,
                    "has_previous_page": False,
                    "next_cursor": "eyJpZCI6IjEyMyIsImNyZWF0ZWRfYXQiOiIyMDI1LTAxLTAxIn0=",
                    "previous_cursor": None,
                    "total_count": 100,
                },
            }
        }
    }


# Advanced transcription feature schemas


class VocabularyTerm(BaseModel):
    """A single vocabulary term with replacement pattern."""

    pattern: str = Field(..., description="Pattern to match (will be regex-escaped)")
    replacement: str = Field(..., description="Replacement text")
    case_sensitive: bool = Field(False, description="Whether matching is case-sensitive")


class VocabularyCreate(BaseModel):
    """Request to create a custom vocabulary."""

    name: str = Field(..., min_length=1, max_length=100, description="Vocabulary name")
    terms: List[VocabularyTerm] = Field(..., description="List of vocabulary terms")
    is_global: bool = Field(False, description="Apply to all jobs (requires admin)")


class VocabularyResponse(BaseModel):
    """Custom vocabulary response."""

    id: uuid.UUID = Field(..., description="Vocabulary ID")
    name: str = Field(..., description="Vocabulary name")
    terms: List[VocabularyTerm] = Field(..., description="List of vocabulary terms")
    is_global: bool = Field(..., description="Whether this is a global vocabulary")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TranslationRequest(BaseModel):
    """Request to translate a transcript."""

    transcript_id: uuid.UUID = Field(..., description="Transcript ID to translate")
    target_language: str = Field(
        ..., min_length=2, max_length=10, description="Target language code (e.g., 'es', 'fr')"
    )
    provider: Optional[Literal["google", "deepl", "libretranslate"]] = Field(
        None, description="Translation provider (uses system default if not specified)"
    )


class TranslationSegment(BaseModel):
    """A translated segment."""

    start_ms: int = Field(..., description="Start time in milliseconds")
    end_ms: int = Field(..., description="End time in milliseconds")
    text: str = Field(..., description="Translated text")
    original_text: Optional[str] = Field(None, description="Original text before translation")


class TranslationResponse(BaseModel):
    """Translation response."""

    id: uuid.UUID = Field(..., description="Translation ID")
    transcript_id: uuid.UUID = Field(..., description="Source transcript ID")
    target_language: str = Field(..., description="Target language code")
    provider: str = Field(..., description="Translation provider used")
    segments: List[TranslationSegment] = Field(..., description="Translated segments")
    full_text: Optional[str] = Field(None, description="Full translated text")
    created_at: datetime = Field(..., description="Translation timestamp")


class ConfidenceFilter(BaseModel):
    """Filter segments by confidence score."""

    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum confidence score")
    max_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Maximum confidence score")


class EnhancedSegment(Segment):
    """Segment with additional metadata."""

    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")
    word_timestamps: Optional[List[Dict[str, Any]]] = Field(None, description="Word-level timestamps")
    avg_logprob: Optional[float] = Field(None, description="Average log probability")
    temperature: Optional[float] = Field(None, description="Sampling temperature used")


class TranscriptMetadata(BaseModel):
    """Metadata about a transcript."""

    detected_language: Optional[str] = Field(None, description="Detected language code")
    language_probability: Optional[float] = Field(None, description="Language detection confidence")
    model: str = Field(..., description="Whisper model used")
    quality_preset: Optional[str] = Field(None, description="Quality preset used")


# Transcript cleanup schemas


class CleanupConfig(BaseModel):
    """Configuration for transcript cleanup operations."""

    # Normalization
    normalize_unicode: bool = Field(True, description="Apply Unicode NFC normalization")
    normalize_whitespace: bool = Field(True, description="Normalize whitespace characters")
    remove_special_tokens: bool = Field(True, description="Remove [MUSIC], [APPLAUSE], etc.")
    preserve_sound_events: bool = Field(False, description="Keep sound event markers when cleaning")

    # Punctuation
    add_punctuation: bool = Field(True, description="Add sentence-ending punctuation")
    punctuation_mode: Literal["none", "rule-based", "model-based"] = Field(
        "rule-based", description="Punctuation restoration strategy"
    )
    add_internal_punctuation: bool = Field(False, description="Add commas and internal punctuation")
    capitalize: bool = Field(True, description="Capitalize sentence-initial letters")
    fix_all_caps: bool = Field(True, description="Fix inappropriate all-caps text")

    # De-filler
    remove_fillers: bool = Field(True, description="Enable filler word removal")
    filler_level: int = Field(1, ge=0, le=3, description="Filler removal level (0-3)")

    # Segmentation
    segment_sentences: bool = Field(True, description="Split segments on sentence boundaries")
    merge_short_segments: bool = Field(True, description="Merge segments with small gaps")
    min_segment_length_ms: int = Field(1000, ge=0, description="Minimum segment duration in ms")
    max_gap_for_merge_ms: int = Field(500, ge=0, description="Maximum gap for merging segments in ms")
    speaker_format: Literal["inline", "dialogue", "structured"] = Field(
        "structured", description="Speaker label formatting style"
    )

    # Advanced
    detect_hallucinations: bool = Field(True, description="Detect and mark potential hallucinations")
    language_specific_rules: bool = Field(True, description="Apply language-specific cleanup rules")

    model_config = {
        "json_schema_extra": {
            "example": {
                "normalize_unicode": True,
                "remove_fillers": True,
                "filler_level": 1,
                "add_punctuation": True,
                "punctuation_mode": "rule-based",
                "capitalize": True,
            }
        }
    }


class CleanupProfile(BaseModel):
    """Predefined cleanup configuration profile."""

    name: str = Field(..., description="Profile name")
    description: str = Field(..., description="Profile description")
    config: CleanupConfig = Field(..., description="Cleanup configuration")


class CleanedSegment(BaseModel):
    """Transcript segment with cleaned text."""

    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    text_raw: str = Field(..., description="Original text before cleanup")
    text_cleaned: str = Field(..., description="Text after cleanup applied")
    speaker_label: Optional[str] = Field(None, description="Speaker label from diarization")
    sentence_boundary: bool = Field(False, description="True if this segment ends a sentence")
    likely_hallucination: bool = Field(False, description="True if detected as potential hallucination")

    model_config = {
        "json_schema_extra": {
            "example": {
                "start_ms": 1000,
                "end_ms": 3500,
                "text_raw": "um hello everyone and uh welcome",
                "text_cleaned": "Hello everyone and welcome.",
                "speaker_label": "Speaker 1",
                "sentence_boundary": True,
                "likely_hallucination": False,
            }
        }
    }


class CleanupStats(BaseModel):
    """Statistics about cleanup operations performed."""

    fillers_removed: int = Field(0, description="Number of filler words removed")
    special_tokens_removed: int = Field(0, description="Number of special tokens removed")
    segments_merged: int = Field(0, description="Number of segments merged")
    segments_split: int = Field(0, description="Number of segments split")
    hallucinations_detected: int = Field(0, description="Number of hallucinations detected")
    punctuation_added: int = Field(0, description="Number of punctuation marks added")


class CleanedTranscriptResponse(BaseModel):
    """Response containing cleaned transcript segments."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    segments: List[CleanedSegment] = Field(..., description="Cleaned transcript segments")
    cleanup_config: CleanupConfig = Field(..., description="Cleanup configuration used")
    stats: CleanupStats = Field(..., description="Statistics about cleanup operations")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of cleanup")

    model_config = {
        "json_schema_extra": {
            "example": {
                "video_id": "123e4567-e89b-12d3-a456-426614174000",
                "segments": [
                    {
                        "start_ms": 1000,
                        "end_ms": 3500,
                        "text_raw": "um hello everyone",
                        "text_cleaned": "Hello everyone.",
                        "speaker_label": "Speaker 1",
                        "sentence_boundary": True,
                    }
                ],
                "cleanup_config": {"remove_fillers": True, "filler_level": 1},
                "stats": {"fillers_removed": 1, "punctuation_added": 1},
            }
        }
    }


class TranscriptBlockResponse(BaseModel):
    """A persisted or derived formatted transcript block."""

    block_index: int = Field(..., description="Zero-based block order")
    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    speaker_label: Optional[str] = Field(None, description="Speaker label for the block")
    text: str = Field(..., description="Formatted block text")
    segment_ids: List[int] = Field(..., description="Source segment indices included in the block")
    kind: Literal["paragraph", "speaker_turn"] = Field(..., description="Block kind")
    formatter_version: str = Field(..., description="Formatter version used to build the block")
    primary_source: Optional[Literal["whisper", "youtube", "merged"]] = Field(None, description="Primary source selected for this block")
    supporting_sources: List[Literal["whisper", "youtube"]] = Field(default_factory=list, description="Sources that supported or contributed to this block")
    needs_review: bool = Field(False, description="True when source disagreement should be reviewed")
    merge_reason: Optional[str] = Field(None, description="Deterministic merge decision reason")
    similarity: Optional[float] = Field(None, description="Token similarity between Whisper and YouTube text for this block")


class FormattedTranscriptResponse(BaseModel):
    """Response containing formatted transcript text."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    segments: List[Segment] = Field(..., description="Raw transcript segments used for seeking and search mapping")
    text: str = Field(..., description="Formatted transcript text")
    format: Literal["inline", "dialogue", "structured"] = Field(..., description="Formatting style used")
    cleanup_config: CleanupConfig = Field(..., description="Cleanup configuration used")
    blocks: List[TranscriptBlockResponse] = Field(default_factory=list, description="Formatted transcript blocks")
    source: Literal["whisper", "youtube", "merged"] = Field("whisper", description="Transcript source used for this response")
    source_label: str = Field("Whisper transcript", description="Human-readable transcript source label")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of formatting"
    )
