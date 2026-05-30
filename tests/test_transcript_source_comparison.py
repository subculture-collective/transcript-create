from app.transcripts.comparison import compare_sources, render_markdown_report
from app.transcripts.types import TranscriptSegment


def test_compare_sources_detects_youtube_gap_fill():
    whisper = [TranscriptSegment(start_ms=0, end_ms=5000, text="hello world", speaker_label=None)]
    youtube = [
        TranscriptSegment(start_ms=0, end_ms=5000, text="hello world", speaker_label=None),
        TranscriptSegment(start_ms=5000, end_ms=10000, text="extra caption text", speaker_label=None),
    ]

    result = compare_sources("video-1", whisper, youtube, bucket_ms=5000)

    assert result["video_id"] == "video-1"
    assert result["total_bucket_count"] == 2
    assert result["whisper"]["coverage_ratio"] == 0.5
    assert result["youtube"]["coverage_ratio"] == 1.0
    assert result["whisper"]["missing_bucket_count"] == 1
    assert result["youtube"]["missing_bucket_count"] == 0
    assert result["youtube_only_bucket_count"] == 1
    assert result["recommendation"] in {"youtube_first", "hybrid"}


def test_compare_sources_recommends_hybrid_for_complementary_gaps():
    whisper = [TranscriptSegment(start_ms=0, end_ms=5000, text="first part", speaker_label=None)]
    youtube = [TranscriptSegment(start_ms=5000, end_ms=10000, text="second part", speaker_label=None)]

    result = compare_sources("video-2", whisper, youtube, bucket_ms=5000)

    assert result["whisper_only_bucket_count"] == 1
    assert result["youtube_only_bucket_count"] == 1
    assert result["recommendation"] == "hybrid"


def test_render_markdown_report_includes_recommendation_counts():
    report = {
        "summary": {
            "video_count": 1,
            "recommendations": {"hybrid": 1},
            "bucket_ms": 10000,
            "average_whisper_coverage": 0.5,
            "average_youtube_coverage": 1.0,
            "average_similarity": 0.75,
        },
        "videos": [
            {
                "video_id": "video-1",
                "title": "Example",
                "recommendation": "hybrid",
                "metrics": {
                    "whisper": {"coverage_ratio": 0.5, "average_similarity": 0.75},
                    "youtube": {"coverage_ratio": 1.0},
                },
            }
        ],
    }

    markdown = render_markdown_report(report)

    assert "# Transcript Source Comparison" in markdown
    assert "hybrid" in markdown
    assert "Example" in markdown
    assert "50.0%" in markdown
