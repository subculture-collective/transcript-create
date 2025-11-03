"""
Baseline test fixtures for transcript formatter regression testing.

Provides sample inputs and expected outputs for various scenarios:
- Whisper transcripts with fillers and artifacts
- YouTube captions
- Multilingual content
- Edge cases
"""

# Sample raw Whisper output with common issues
WHISPER_RAW_SAMPLE = [
    {"text": "um hello everyone", "start": 0, "end": 2000},
    {"text": "uh today we're going to talk about", "start": 2000, "end": 5000},
    {"text": "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING", "start": 5000, "end": 8000},
    {"text": "[MUSIC] it's really interesting [MUSIC]", "start": 8000, "end": 11000},
    {"text": "like you know i think it's the future", "start": 11000, "end": 14000},
    {"text": "so basically we should learn more", "start": 14000, "end": 17000},
    {"text": "  ", "start": 17000, "end": 18000},  # Empty/hallucination
    {"text": "Thank you.", "start": 18000, "end": 19000},  # Common hallucination
]

# Expected output with default formatting
WHISPER_FORMATTED_SAMPLE = [
    {"text": "Hello everyone.", "start": 0, "end": 2000},
    {"text": "Today we're going to talk about.", "start": 2000, "end": 5000},
    {"text": "Artificial intelligence and machine learning.", "start": 5000, "end": 8000},
    {"text": "It's really interesting.", "start": 8000, "end": 11000},
    {"text": "I think it's the future.", "start": 11000, "end": 14000},
    {"text": "We should learn more.", "start": 14000, "end": 17000},
]

# YouTube caption sample (typically already clean)
YOUTUBE_CAPTION_SAMPLE = [
    {"text": "Hello and welcome", "start": 0, "end": 2000},
    {"text": "to this video tutorial", "start": 2000, "end": 4000},
    {"text": "we will cover the basics", "start": 4000, "end": 6000},
]

YOUTUBE_FORMATTED_SAMPLE = [
    {"text": "Hello and welcome.", "start": 0, "end": 2000},
    {"text": "To this video tutorial.", "start": 2000, "end": 4000},
    {"text": "We will cover the basics.", "start": 4000, "end": 6000},
]

# Multilingual sample
MULTILINGUAL_SAMPLE = [
    {"text": "hello world", "start": 0, "end": 2000},
    {"text": "bonjour le monde", "start": 2000, "end": 4000},
    {"text": "hola mundo", "start": 4000, "end": 6000},
    {"text": "こんにちは世界", "start": 6000, "end": 8000},
]

MULTILINGUAL_FORMATTED_SAMPLE = [
    {"text": "Hello world.", "start": 0, "end": 2000},
    {"text": "Bonjour le monde.", "start": 2000, "end": 4000},
    {"text": "Hola mundo.", "start": 4000, "end": 6000},
    {"text": "こんにちは世界.", "start": 6000, "end": 8000},
]

# Diarized conversation sample
DIARIZED_CONVERSATION_SAMPLE = [
    {"text": "Hi there", "start": 0, "end": 1000, "speaker": "Speaker 1"},
    {"text": "How are you doing", "start": 1000, "end": 2500, "speaker": "Speaker 1"},
    {"text": "I'm doing great thanks", "start": 2500, "end": 4000, "speaker": "Speaker 2"},
    {"text": "How about you", "start": 4000, "end": 5000, "speaker": "Speaker 2"},
    {"text": "Pretty good", "start": 5000, "end": 6000, "speaker": "Speaker 1"},
]

DIARIZED_STRUCTURED_FORMAT = [
    {"text": "Speaker 1: Hi there.", "start": 0, "end": 1000, "speaker": "Speaker 1"},
    {"text": "How are you doing.", "start": 1000, "end": 2500, "speaker": "Speaker 1"},
    {"text": "Speaker 2: I'm doing great thanks.", "start": 2500, "end": 4000, "speaker": "Speaker 2"},
    {"text": "How about you.", "start": 4000, "end": 5000, "speaker": "Speaker 2"},
    {"text": "Speaker 1: Pretty good.", "start": 5000, "end": 6000, "speaker": "Speaker 1"},
]

DIARIZED_DIALOGUE_FORMAT = [
    {"text": "Speaker 1: Hi there.", "start": 0, "end": 1000, "speaker": "Speaker 1"},
    {"text": "Speaker 1: How are you doing.", "start": 1000, "end": 2500, "speaker": "Speaker 1"},
    {"text": "Speaker 2: I'm doing great thanks.", "start": 2500, "end": 4000, "speaker": "Speaker 2"},
    {"text": "Speaker 2: How about you.", "start": 4000, "end": 5000, "speaker": "Speaker 2"},
    {"text": "Speaker 1: Pretty good.", "start": 5000, "end": 6000, "speaker": "Speaker 1"},
]

# Long segment for sentence splitting
LONG_SEGMENT_SAMPLE = [
    {
        "text": "This is a long segment with multiple sentences. It should be split. Each sentence gets its own segment.",
        "start": 0,
        "end": 10000,
    }
]

# Sample with short segments to merge
SHORT_SEGMENTS_SAMPLE = [
    {"text": "Hi", "start": 0, "end": 300},
    {"text": "there", "start": 400, "end": 700},
    {"text": "friend", "start": 800, "end": 1100},
    {"text": "This is a longer segment", "start": 5000, "end": 8000},
]

# Sample with special characters
SPECIAL_CHARS_SAMPLE = [
    {"text": "the price is $19.99", "start": 0, "end": 2000},
    {"text": "email me at test@example.com", "start": 2000, "end": 4000},
    {"text": "math: 2 + 2 = 4", "start": 4000, "end": 6000},
    {"text": "it's 50% off", "start": 6000, "end": 8000},
]

SPECIAL_CHARS_FORMATTED = [
    {"text": "The price is $19.99.", "start": 0, "end": 2000},
    {"text": "Email me at test@example.com.", "start": 2000, "end": 4000},
    {"text": "Math: 2 + 2 = 4.", "start": 4000, "end": 6000},
    {"text": "It's 50% off.", "start": 6000, "end": 8000},
]

# Edge case: empty and whitespace-only segments
EDGE_CASE_EMPTY = [
    {"text": "Valid text", "start": 0, "end": 1000},
    {"text": "   ", "start": 1000, "end": 2000},
    {"text": "", "start": 2000, "end": 3000},
    {"text": "Another valid", "start": 3000, "end": 4000},
]

EDGE_CASE_EMPTY_FORMATTED = [
    {"text": "Valid text.", "start": 0, "end": 1000},
    {"text": "Another valid.", "start": 3000, "end": 4000},
]
