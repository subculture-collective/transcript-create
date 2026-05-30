from worker.loop import pending_video_claim_sql
from worker.state_model import OPEN_CAPTION_INGEST_STATES, TERMINAL_CAPTION_INGEST_STATES


def test_pending_video_claim_sql_blocks_until_expected_jobs_expanded():
    sql = pending_video_claim_sql()

    assert "j2.state <> 'pending'" in sql
    assert "EXISTS (SELECT 1 FROM videos v3 WHERE v3.job_id = j2.id)" in sql
    assert "batch_expected_jobs" in sql


def test_pending_video_claim_sql_waits_for_open_caption_work_to_finish():
    sql = pending_video_claim_sql()

    for state in OPEN_CAPTION_INGEST_STATES:
        assert f"'{state}'" in sql
    assert "NOT EXISTS" in sql


def test_pending_video_claim_sql_treats_caption_failures_as_terminal_for_whisper_fallback():
    sql = pending_video_claim_sql()

    for state in TERMINAL_CAPTION_INGEST_STATES:
        assert f"'{state}'" in sql


def test_pending_video_claim_sql_prioritizes_videos_without_youtube_captions():
    sql = pending_video_claim_sql()

    assert "youtube_transcripts" in sql
    assert "yt.video_id = v.id" in sql
    assert "THEN 1" in sql
    assert "ELSE 0" in sql
