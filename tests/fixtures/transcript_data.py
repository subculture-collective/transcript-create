"""Sample transcript data for testing."""

SAMPLE_WHISPER_SEGMENTS = [
    {
        "id": 0,
        "start": 0.0,
        "end": 2.5,
        "text": " Hello and welcome to this test video.",
        "tokens": [1, 2, 3],
        "temperature": 0.0,
        "avg_logprob": -0.3,
        "compression_ratio": 1.5,
        "no_speech_prob": 0.01,
    },
    {
        "id": 1,
        "start": 2.5,
        "end": 5.0,
        "text": " Today we're going to test the transcription system.",
        "tokens": [4, 5, 6],
        "temperature": 0.0,
        "avg_logprob": -0.25,
        "compression_ratio": 1.6,
        "no_speech_prob": 0.02,
    },
    {
        "id": 2,
        "start": 5.0,
        "end": 8.0,
        "text": " This is a sample transcript with multiple speakers.",
        "tokens": [7, 8, 9],
        "temperature": 0.0,
        "avg_logprob": -0.28,
        "compression_ratio": 1.55,
        "no_speech_prob": 0.015,
    },
]

SAMPLE_DIARIZED_SEGMENTS = [
    {
        "start": 0.0,
        "end": 2.5,
        "text": " Hello and welcome to this test video.",
        "speaker": 0,
        "speaker_label": "Speaker 1",
    },
    {
        "start": 2.5,
        "end": 5.0,
        "text": " Today we're going to test the transcription system.",
        "speaker": 0,
        "speaker_label": "Speaker 1",
    },
    {
        "start": 5.0,
        "end": 8.0,
        "text": " This is a sample transcript with multiple speakers.",
        "speaker": 1,
        "speaker_label": "Speaker 2",
    },
]

SAMPLE_SRT_OUTPUT = """1
00:00:00,000 --> 00:00:02,500
Hello and welcome to this test video.

2
00:00:02,500 --> 00:00:05,000
Today we're going to test the transcription system.

3
00:00:05,000 --> 00:00:08,000
This is a sample transcript with multiple speakers.
"""

SAMPLE_VTT_OUTPUT = """WEBVTT

00:00:00.000 --> 00:00:02.500
Hello and welcome to this test video.

00:00:02.500 --> 00:00:05.000
Today we're going to test the transcription system.

00:00:05.000 --> 00:00:08.000
This is a sample transcript with multiple speakers.
"""

# Database-ready segment format
DB_SEGMENTS = [
    {
        "idx": 0,
        "start_ms": 0,
        "end_ms": 2500,
        "text": "Hello and welcome to this test video.",
        "speaker": 0,
        "speaker_label": "Speaker 1",
        "confidence": 0.95,
    },
    {
        "idx": 1,
        "start_ms": 2500,
        "end_ms": 5000,
        "text": "Today we're going to test the transcription system.",
        "speaker": 0,
        "speaker_label": "Speaker 1",
        "confidence": 0.92,
    },
    {
        "idx": 2,
        "start_ms": 5000,
        "end_ms": 8000,
        "text": "This is a sample transcript with multiple speakers.",
        "speaker": 1,
        "speaker_label": "Speaker 2",
        "confidence": 0.94,
    },
]
