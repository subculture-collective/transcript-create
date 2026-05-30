from worker.state_model import (
    CaptionIngestState,
    DiarizationState,
    JobState,
    VideoState,
    can_start_native_transcription,
    job_state_from_video_states,
)


def test_job_completes_when_all_videos_completed():
    assert job_state_from_video_states([VideoState.COMPLETED, VideoState.COMPLETED]) == JobState.COMPLETED


def test_job_fails_when_no_active_videos_and_any_failed():
    assert job_state_from_video_states([VideoState.COMPLETED, VideoState.FAILED]) == JobState.FAILED


def test_job_keeps_running_with_pending_video():
    assert job_state_from_video_states([VideoState.COMPLETED, VideoState.PENDING]) == JobState.DOWNLOADING


def test_staged_video_cannot_start_native_until_caption_terminal():
    assert not can_start_native_transcription(
        staged=True,
        own_caption_state=CaptionIngestState.PENDING,
        batch_job_count=3,
        expected_batch_jobs=3,
        batch_has_open_caption_work=True,
    )


def test_staged_video_can_start_native_after_all_captions_terminal():
    for state in (
        CaptionIngestState.COMPLETED,
        CaptionIngestState.UNAVAILABLE,
        CaptionIngestState.FAILED,
        CaptionIngestState.SKIPPED,
    ):
        assert can_start_native_transcription(
            staged=True,
            own_caption_state=state,
            batch_job_count=3,
            expected_batch_jobs=3,
            batch_has_open_caption_work=False,
        )


def test_staged_batch_waits_for_all_expected_jobs():
    assert not can_start_native_transcription(
        staged=True,
        own_caption_state=CaptionIngestState.COMPLETED,
        batch_job_count=2,
        expected_batch_jobs=3,
        batch_has_open_caption_work=False,
    )


def test_diarization_states_include_failed_and_skipped():
    assert DiarizationState.FAILED.value == "failed"
    assert DiarizationState.SKIPPED.value == "skipped"


def test_video_state_model_includes_db_enum_states():
    assert VideoState.DIARIZING.value == "diarizing"
    assert VideoState.PERSISTING.value == "persisting"
    assert VideoState.EXPANDED.value == "expanded"
