# Transcript Cleanup Examples and Test Cases

This document provides concrete examples of transcript cleanup transformations for testing and validation.

## Table of Contents

1. [Basic Normalization Examples](#basic-normalization-examples)
2. [Punctuation Restoration Examples](#punctuation-restoration-examples)
3. [Filler Removal Examples](#filler-removal-examples)
4. [Segmentation Examples](#segmentation-examples)
5. [Speaker Formatting Examples](#speaker-formatting-examples)
6. [Edge Cases](#edge-cases)
7. [Test Data Fixtures](#test-data-fixtures)

---

## Basic Normalization Examples

### Example 1: Whitespace Normalization

**Input**:
```
"Hello  world   test\u00A0string"
```

**Expected Output**:
```
"Hello world test string"
```

**Transformations**: Replace Unicode nbsp with space, collapse multiple spaces

---

### Example 2: Special Token Removal

**Input**:
```
"[MUSIC] Welcome to the show [APPLAUSE] Let's get started"
```

**Expected Output**:
```
"Welcome to the show Let's get started"
```

**Transformations**: Remove [MUSIC] and [APPLAUSE] tokens

---

### Example 3: Unicode Normalization

**Input**:
```
"café" (composed as c + a + f + e ́)
```

**Expected Output**:
```
"café" (NFC normalized)
```

**Transformations**: Apply NFC normalization

---

## Punctuation Restoration Examples

### Example 4: Add Sentence-Ending Punctuation

**Input**:
```
"hello everyone and welcome to the show"
```

**Expected Output**:
```
"hello everyone and welcome to the show."
```

**Transformations**: Add period at end

---

### Example 5: Question Detection

**Input**:
```
"what time is it"
```

**Expected Output**:
```
"What time is it?"
```

**Transformations**: Detect interrogative word, add question mark, capitalize

---

### Example 6: Capitalization

**Input**:
```
"hello. world. how are you."
```

**Expected Output**:
```
"Hello. World. How are you."
```

**Transformations**: Capitalize after sentence boundaries

---

### Example 7: All-Caps Fix

**Input**:
```
"HELLO EVERYONE WELCOME TO THE SHOW"
```

**Expected Output**:
```
"Hello everyone welcome to the show."
```

**Transformations**: Convert inappropriate all-caps to sentence case

---

## Filler Removal Examples

### Example 8: Level 1 - Conservative

**Input**:
```
"um hello everyone uh welcome to er the show"
```

**Expected Output**:
```
"hello everyone welcome to the show"
```

**Transformations**: Remove um, uh, er

---

### Example 9: Level 2 - Moderate

**Input**:
```
"I I I think you know it's really good"
```

**Expected Output**:
```
"I think it's really good"
```

**Transformations**: Remove stutters (I I I → I), remove filler phrases (you know)

---

### Example 10: Level 3 - Aggressive

**Input**:
```
"so like I think you know it's kind of really good"
```

**Expected Output**:
```
"I think it's really good"
```

**Transformations**: Remove so, like, you know, kind of

---

## Segmentation Examples

### Example 11: Sentence Splitting

**Input** (single segment):
```
{
  "text": "Hello everyone. Welcome to the show. Let's get started.",
  "start_ms": 0,
  "end_ms": 5000
}
```

**Expected Output** (three segments):
```json
[
  {"text": "Hello everyone.", "start_ms": 0, "end_ms": 1666},
  {"text": "Welcome to the show.", "start_ms": 1666, "end_ms": 3333},
  {"text": "Let's get started.", "start_ms": 3333, "end_ms": 5000}
]
```

**Transformations**: Split on sentence boundaries, divide time proportionally

---

### Example 12: Segment Merging

**Input** (three segments with small gaps):
```json
[
  {"text": "Hello", "start_ms": 0, "end_ms": 500},
  {"text": "everyone", "start_ms": 550, "end_ms": 1200},
  {"text": "welcome", "start_ms": 1250, "end_ms": 2000}
]
```

**Expected Output** (one merged segment):
```json
[
  {"text": "Hello everyone welcome.", "start_ms": 0, "end_ms": 2000}
]
```

**Transformations**: Merge segments with gaps < 500ms, add punctuation

---

### Example 13: Hallucination Detection

**Input**:
```json
[
  {"text": "Welcome to my channel", "start_ms": 0, "end_ms": 2000},
  {"text": "Thanks for watching", "start_ms": 10000, "end_ms": 12000},
  {"text": "Thanks for watching", "start_ms": 12000, "end_ms": 14000},
  {"text": "Thanks for watching", "start_ms": 14000, "end_ms": 16000}
]
```

**Expected Output**:
```json
[
  {"text": "Welcome to my channel.", "start_ms": 0, "end_ms": 2000},
  {
    "text": "Thanks for watching.",
    "start_ms": 10000,
    "end_ms": 12000,
    "likely_hallucination": false
  },
  {
    "text": "Thanks for watching.",
    "start_ms": 12000,
    "end_ms": 14000,
    "likely_hallucination": true
  },
  {
    "text": "Thanks for watching.",
    "start_ms": 14000,
    "end_ms": 16000,
    "likely_hallucination": true
  }
]
```

**Transformations**: Detect repetitive segments, mark as likely hallucinations

---

## Speaker Formatting Examples

### Example 14: Structured Format (API Default)

**Input**:
```json
[
  {"speaker_label": "SPEAKER_00", "text": "Hello everyone", "start_ms": 0, "end_ms": 1500},
  {"speaker_label": "SPEAKER_00", "text": "welcome to the show", "start_ms": 1500, "end_ms": 3000},
  {"speaker_label": "SPEAKER_01", "text": "thanks for having me", "start_ms": 3500, "end_ms": 5000}
]
```

**Expected Output** (structured):
```json
[
  {
    "speaker_label": "Speaker 1",
    "text_cleaned": "Hello everyone, welcome to the show.",
    "start_ms": 0,
    "end_ms": 3000
  },
  {
    "speaker_label": "Speaker 2",
    "text_cleaned": "Thanks for having me.",
    "start_ms": 3500,
    "end_ms": 5000
  }
]
```

---

### Example 15: Dialogue Format

**Input**: Same as Example 14

**Expected Output** (text):
```
Speaker 1: Hello everyone, welcome to the show.

Speaker 2: Thanks for having me.
```

---

### Example 16: Inline Format

**Input**: Same as Example 14

**Expected Output** (text):
```
[Speaker 1] Hello everyone, welcome to the show.
[Speaker 2] Thanks for having me.
```

---

## Edge Cases

### Example 17: Abbreviations

**Input**:
```
"Dr. Smith said the U.S. economy is strong. Prof. Jones agreed."
```

**Expected Output**:
```
"Dr. Smith said the U.S. economy is strong. Prof. Jones agreed."
```

**Note**: Should NOT split after "Dr." or "U.S."

---

### Example 18: Quoted Speech

**Input**:
```
"He said what time is it and left"
```

**Expected Output**:
```
"He said, \"What time is it?\" and left."
```

**Note**: This is an advanced case that may not be handled in v1

---

### Example 19: Mixed Language

**Input**:
```
"Hello! ¿Cómo estás? I'm fine."
```

**Expected Output**:
```
"Hello! ¿Cómo estás? I'm fine."
```

**Note**: Preserve language-specific punctuation

---

### Example 20: URLs and Technical Terms

**Input**:
```
"visit github.com slash user slash repo for the code"
```

**Expected Output**:
```
"Visit github.com slash user slash repo for the code."
```

**Note**: Preserve technical content, minimal changes

---

### Example 21: Empty Segments

**Input**:
```
[
  {"text": "um", "start_ms": 0, "end_ms": 200},
  {"text": "uh", "start_ms": 200, "end_ms": 400},
  {"text": "hello", "start_ms": 500, "end_ms": 1000}
]
```

**Expected Output**:
```
[
  {"text_cleaned": "Hello.", "start_ms": 500, "end_ms": 1000}
]
```

**Note**: First two segments are only fillers, removed entirely

---

## Test Data Fixtures

### Fixture 1: YouTube Auto-Caption Sample

```json
{
  "name": "youtube_tech_talk",
  "description": "Tech talk with moderate fillers and special tokens",
  "raw_segments": [
    {"text": "[Music]", "start_ms": 0, "end_ms": 2000},
    {"text": "so um hello everyone", "start_ms": 2000, "end_ms": 4000},
    {"text": "welcome to uh the show", "start_ms": 4000, "end_ms": 6000},
    {"text": "[Applause]", "start_ms": 6000, "end_ms": 7000},
    {"text": "today we're gonna talk about docker", "start_ms": 7000, "end_ms": 9500}
  ],
  "expected_cleaned_level_1": [
    {"text_cleaned": "Hello everyone.", "start_ms": 2000, "end_ms": 4000},
    {"text_cleaned": "Welcome to the show.", "start_ms": 4000, "end_ms": 6000},
    {"text_cleaned": "Today we're going to talk about Docker.", "start_ms": 7000, "end_ms": 9500}
  ],
  "expected_stats": {
    "fillers_removed": 2,
    "special_tokens_removed": 2,
    "segments_merged": 0,
    "punctuation_added": 3
  }
}
```

---

### Fixture 2: Whisper Output with Hallucination

```json
{
  "name": "whisper_with_hallucination",
  "description": "Whisper transcript with end repetition hallucination",
  "raw_segments": [
    {"text": "Welcome to my channel.", "start_ms": 0, "end_ms": 2000},
    {"text": "If you enjoyed this video, please like and subscribe.", "start_ms": 2000, "end_ms": 5000},
    {"text": "Thanks for watching!", "start_ms": 5000, "end_ms": 6500},
    {"text": "Thanks for watching!", "start_ms": 6500, "end_ms": 8000},
    {"text": "Thanks for watching!", "start_ms": 8000, "end_ms": 9500}
  ],
  "expected_cleaned": [
    {"text_cleaned": "Welcome to my channel.", "start_ms": 0, "end_ms": 2000, "likely_hallucination": false},
    {"text_cleaned": "If you enjoyed this video, please like and subscribe.", "start_ms": 2000, "end_ms": 5000, "likely_hallucination": false},
    {"text_cleaned": "Thanks for watching!", "start_ms": 5000, "end_ms": 6500, "likely_hallucination": false},
    {"text_cleaned": "Thanks for watching!", "start_ms": 6500, "end_ms": 8000, "likely_hallucination": true},
    {"text_cleaned": "Thanks for watching!", "start_ms": 8000, "end_ms": 9500, "likely_hallucination": true}
  ],
  "expected_stats": {
    "hallucinations_detected": 2
  }
}
```

---

### Fixture 3: Multi-Speaker Conversation

```json
{
  "name": "interview_multi_speaker",
  "description": "Interview with two speakers and diarization",
  "raw_segments": [
    {"speaker_label": "SPEAKER_00", "text": "um hello everyone", "start_ms": 0, "end_ms": 1500},
    {"speaker_label": "SPEAKER_00", "text": "welcome to the podcast", "start_ms": 1500, "end_ms": 3000},
    {"speaker_label": "SPEAKER_01", "text": "uh thanks for having me", "start_ms": 3500, "end_ms": 5000},
    {"speaker_label": "SPEAKER_01", "text": "excited to be here", "start_ms": 5000, "end_ms": 6500},
    {"speaker_label": "SPEAKER_00", "text": "so let's start with you know your background", "start_ms": 7000, "end_ms": 9000}
  ],
  "expected_cleaned_structured": [
    {
      "speaker_label": "Speaker 1",
      "text_cleaned": "Hello everyone, welcome to the podcast.",
      "start_ms": 0,
      "end_ms": 3000
    },
    {
      "speaker_label": "Speaker 2",
      "text_cleaned": "Thanks for having me, excited to be here.",
      "start_ms": 3500,
      "end_ms": 6500
    },
    {
      "speaker_label": "Speaker 1",
      "text_cleaned": "So let's start with your background.",
      "start_ms": 7000,
      "end_ms": 9000
    }
  ],
  "expected_cleaned_dialogue": "Speaker 1: Hello everyone, welcome to the podcast.\n\nSpeaker 2: Thanks for having me, excited to be here.\n\nSpeaker 1: So let's start with your background.",
  "expected_stats": {
    "fillers_removed": 4,
    "segments_merged": 4,
    "punctuation_added": 3
  }
}
```

---

### Fixture 4: All-Caps with Technical Terms

```json
{
  "name": "all_caps_tech",
  "description": "All-caps text with technical terms that should be preserved",
  "raw_segments": [
    {"text": "HELLO EVERYONE TODAY WE'RE TALKING ABOUT CPU AND GPU OPTIMIZATION", "start_ms": 0, "end_ms": 4000},
    {"text": "THE API USES REST AND GRAPHQL", "start_ms": 4000, "end_ms": 7000}
  ],
  "expected_cleaned": [
    {"text_cleaned": "Hello everyone, today we're talking about CPU and GPU optimization.", "start_ms": 0, "end_ms": 4000},
    {"text_cleaned": "The API uses REST and GraphQL.", "start_ms": 4000, "end_ms": 7000}
  ],
  "notes": "CPU, GPU, API, REST, GraphQL should remain all-caps (acronyms)"
}
```

---

### Fixture 5: Heavy Fillers

```json
{
  "name": "heavy_fillers",
  "description": "Transcript with many fillers for testing different levels",
  "raw_segments": [
    {"text": "so um like I think you know it's kind of really good actually", "start_ms": 0, "end_ms": 3000},
    {"text": "uh basically I mean it's sort of interesting right", "start_ms": 3000, "end_ms": 6000}
  ],
  "expected_cleaned_level_1": [
    {"text_cleaned": "So like I think you know it's kind of really good actually.", "start_ms": 0, "end_ms": 3000},
    {"text_cleaned": "Basically I mean it's sort of interesting right.", "start_ms": 3000, "end_ms": 6000}
  ],
  "expected_cleaned_level_2": [
    {"text_cleaned": "So like I think it's kind of really good actually.", "start_ms": 0, "end_ms": 3000},
    {"text_cleaned": "Basically it's sort of interesting right.", "start_ms": 3000, "end_ms": 6000}
  ],
  "expected_cleaned_level_3": [
    {"text_cleaned": "I think it's really good.", "start_ms": 0, "end_ms": 3000},
    {"text_cleaned": "It's interesting.", "start_ms": 3000, "end_ms": 6000}
  ],
  "notes": "Shows progression of filler removal at different levels"
}
```

---

## Unit Test Template

Here's a template for creating unit tests based on these examples:

```python
import pytest
from worker.cleanup import apply_cleanup
from app.schemas import CleanupConfig

class TestBasicNormalization:
    def test_whitespace_normalization(self):
        """Test Example 1: Whitespace normalization"""
        input_text = "Hello  world   test\u00A0string"
        expected = "Hello world test string"
        
        config = CleanupConfig(
            normalize_whitespace=True,
            add_punctuation=False
        )
        
        segments = [{"text": input_text, "start_ms": 0, "end_ms": 1000}]
        result = apply_cleanup(segments, config)
        
        assert result[0]["text_cleaned"] == expected
    
    def test_special_token_removal(self):
        """Test Example 2: Special token removal"""
        input_text = "[MUSIC] Welcome to the show [APPLAUSE] Let's get started"
        expected = "Welcome to the show Let's get started"
        
        config = CleanupConfig(
            remove_special_tokens=True,
            add_punctuation=False
        )
        
        segments = [{"text": input_text, "start_ms": 0, "end_ms": 1000}]
        result = apply_cleanup(segments, config)
        
        assert "[MUSIC]" not in result[0]["text_cleaned"]
        assert "[APPLAUSE]" not in result[0]["text_cleaned"]


class TestPunctuationRestoration:
    def test_add_sentence_punctuation(self):
        """Test Example 4: Add sentence-ending punctuation"""
        input_text = "hello everyone and welcome to the show"
        expected = "hello everyone and welcome to the show."
        
        config = CleanupConfig(
            add_punctuation=True,
            capitalize=False
        )
        
        segments = [{"text": input_text, "start_ms": 0, "end_ms": 1000}]
        result = apply_cleanup(segments, config)
        
        assert result[0]["text_cleaned"].endswith(".")
    
    def test_question_detection(self):
        """Test Example 5: Question detection"""
        input_text = "what time is it"
        
        config = CleanupConfig(
            add_punctuation=True,
            capitalize=True
        )
        
        segments = [{"text": input_text, "start_ms": 0, "end_ms": 1000}]
        result = apply_cleanup(segments, config)
        
        assert result[0]["text_cleaned"].endswith("?")
        assert result[0]["text_cleaned"][0].isupper()


class TestFillerRemoval:
    @pytest.mark.parametrize("level,expected_has_filler", [
        (0, True),   # Level 0 - no removal
        (1, False),  # Level 1 - should remove "um"
        (2, False),
        (3, False),
    ])
    def test_filler_removal_levels(self, level, expected_has_filler):
        """Test Example 8: Filler removal at different levels"""
        input_text = "um hello everyone"
        
        config = CleanupConfig(
            remove_fillers=True,
            filler_level=level
        )
        
        segments = [{"text": input_text, "start_ms": 0, "end_ms": 1000}]
        result = apply_cleanup(segments, config)
        
        has_filler = "um" in result[0]["text_cleaned"].lower()
        assert has_filler == expected_has_filler


class TestSegmentation:
    def test_hallucination_detection(self):
        """Test Example 13: Hallucination detection"""
        segments = [
            {"text": "Welcome to my channel", "start_ms": 0, "end_ms": 2000},
            {"text": "Thanks for watching", "start_ms": 10000, "end_ms": 12000},
            {"text": "Thanks for watching", "start_ms": 12000, "end_ms": 14000},
            {"text": "Thanks for watching", "start_ms": 14000, "end_ms": 16000},
        ]
        
        config = CleanupConfig(detect_hallucinations=True)
        result = apply_cleanup(segments, config)
        
        # Last two should be marked as hallucinations
        assert result[-1].get("likely_hallucination", False) == True
        assert result[-2].get("likely_hallucination", False) == True
```

---

## Integration Test Template

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_cleanup_api_with_fixture(client: AsyncClient, db_session):
    """Test cleanup API using fixture data"""
    # Load fixture
    fixture = load_fixture("youtube_tech_talk")
    
    # Create video and segments in database
    video_id = await create_test_video(db_session, fixture["raw_segments"])
    
    # Call cleanup API
    response = await client.get(
        f"/videos/{video_id}/transcript?format=cleaned&profile=standard"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify cleanup was applied
    assert len(data["segments"]) == len(fixture["expected_cleaned_level_1"])
    
    # Verify specific transformations
    for actual, expected in zip(data["segments"], fixture["expected_cleaned_level_1"]):
        assert actual["text_cleaned"] == expected["text_cleaned"]
    
    # Verify stats
    assert data["stats"]["fillers_removed"] == fixture["expected_stats"]["fillers_removed"]
```

---

## Performance Benchmarks

Target performance for cleanup operations:

| Operation | Target Time (per 1000 segments) | Notes |
|-----------|--------------------------------|-------|
| Whitespace normalization | < 10ms | Pure regex |
| Special token removal | < 20ms | Regex with patterns |
| Filler removal (level 1) | < 50ms | Simple patterns |
| Filler removal (level 3) | < 100ms | More complex patterns |
| Punctuation (rule-based) | < 100ms | Linguistic rules |
| Sentence splitting | < 150ms | Regex + logic |
| Speaker formatting | < 50ms | Simple grouping |
| **Full cleanup (standard profile)** | **< 500ms** | Combined operations |

---

## Validation Checklist

When implementing cleanup functionality, verify:

- [ ] All normalization examples produce expected output
- [ ] Punctuation is added correctly
- [ ] Questions are detected and formatted properly
- [ ] Capitalization rules are applied consistently
- [ ] Filler removal respects level settings
- [ ] Segmentation preserves timing information
- [ ] Speaker labels are maintained and formatted correctly
- [ ] Hallucination detection works on repetitive segments
- [ ] Edge cases (abbreviations, quotes, mixed language) are handled
- [ ] Performance meets targets
- [ ] API endpoints return correct schemas
- [ ] Configuration profiles work as documented
- [ ] Stats accurately reflect transformations performed

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-02 | Initial examples and test cases |
