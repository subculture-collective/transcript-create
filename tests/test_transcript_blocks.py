from app.transcripts.blocks import build_transcript_blocks
from app.transcripts.types import TranscriptSegment


def test_unlabeled_segments_are_grouped_into_readable_paragraphs():
    segments = [
        TranscriptSegment(start_ms=0, end_ms=900, text="hello everyone\n", speaker_label=None),
        TranscriptSegment(start_ms=950, end_ms=1800, text="this is a test", speaker_label=None),
        TranscriptSegment(start_ms=3400, end_ms=4300, text="new thought starts here", speaker_label=None),
    ]

    blocks = build_transcript_blocks(segments)

    assert len(blocks) == 2
    assert blocks[0].kind == "paragraph"
    assert blocks[0].speaker_label is None
    assert blocks[0].start_ms == 0
    assert blocks[0].end_ms == 1800
    assert blocks[0].segment_ids == [0, 1]
    assert "\n" not in blocks[0].text
    assert blocks[0].text == "Hello everyone. This is a test."
    assert blocks[1].text == "New thought starts here."


def test_speaker_changes_create_speaker_turn_blocks():
    segments = [
        TranscriptSegment(start_ms=0, end_ms=900, text="hello there", speaker_label="Hasan"),
        TranscriptSegment(start_ms=950, end_ms=1800, text="i keep talking", speaker_label="Hasan"),
        TranscriptSegment(start_ms=2000, end_ms=2600, text="short reply", speaker_label="Speaker 2"),
    ]

    blocks = build_transcript_blocks(segments)

    assert len(blocks) == 2
    assert blocks[0].kind == "speaker_turn"
    assert blocks[0].speaker_label == "Hasan"
    assert blocks[0].text == "Hello there. I keep talking."
    assert blocks[0].segment_ids == [0, 1]
    assert blocks[1].speaker_label == "Speaker 2"
    assert blocks[1].text == "Short reply."
