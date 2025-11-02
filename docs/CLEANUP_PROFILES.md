# Transcript Cleanup Configuration Profiles

This document defines predefined cleanup configuration profiles for common use cases. These profiles can be referenced by name in API calls or used as starting points for custom configurations.

## Available Profiles

### minimal

**Description**: Minimal cleanup - only essential normalization, no content changes

**Use Case**: When you want to preserve the original transcript as closely as possible, but fix basic formatting issues

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": false,
  "preserve_sound_events": true,
  "add_punctuation": false,
  "punctuation_mode": "none",
  "capitalize": false,
  "remove_fillers": false,
  "filler_level": 0,
  "segment_sentences": false,
  "merge_short_segments": false
}
```

**Example Transformation**:
```
Input:  "  um  hello   world  "
Output: "um hello world"
```

---

### standard (default)

**Description**: Balanced cleanup with conservative filler removal and basic punctuation

**Use Case**: General-purpose cleanup suitable for most transcripts. Good default for YouTube and Whisper content.

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": true,
  "preserve_sound_events": false,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": false,
  "capitalize": true,
  "fix_all_caps": true,
  "remove_fillers": true,
  "filler_level": 1,
  "segment_sentences": true,
  "merge_short_segments": true,
  "min_segment_length_ms": 1000,
  "max_gap_for_merge_ms": 500,
  "speaker_format": "structured",
  "detect_hallucinations": true,
  "language_specific_rules": true
}
```

**Example Transformation**:
```
Input:  "[MUSIC] um hello everyone uh welcome to the show"
Output: "Hello everyone, welcome to the show."
```

---

### aggressive

**Description**: Maximum cleanup with aggressive filler removal and formatting

**Use Case**: When you want the cleanest possible output and don't mind some semantic changes (e.g., removing "like", "you know")

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": true,
  "preserve_sound_events": false,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": true,
  "capitalize": true,
  "fix_all_caps": true,
  "remove_fillers": true,
  "filler_level": 3,
  "segment_sentences": true,
  "merge_short_segments": true,
  "min_segment_length_ms": 500,
  "max_gap_for_merge_ms": 1000,
  "speaker_format": "dialogue",
  "detect_hallucinations": true,
  "language_specific_rules": true
}
```

**Example Transformation**:
```
Input:  "so like I think you know it's kind of really good"
Output: "I think it's really good."
```

---

### youtube_captions

**Description**: Optimized for cleaning YouTube auto-generated captions

**Use Case**: Processing YouTube auto-captions which often have specific formatting issues

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": true,
  "preserve_sound_events": false,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": false,
  "capitalize": true,
  "fix_all_caps": true,
  "remove_fillers": true,
  "filler_level": 2,
  "segment_sentences": true,
  "merge_short_segments": true,
  "min_segment_length_ms": 800,
  "max_gap_for_merge_ms": 600,
  "speaker_format": "structured",
  "detect_hallucinations": false,
  "language_specific_rules": true
}
```

**Notes**:
- YouTube captions typically don't have hallucinations (unlike Whisper)
- Often have run-on segments that benefit from sentence splitting
- May have moderate fillers that benefit from level 2 removal

---

### whisper_output

**Description**: Optimized for Whisper transcription output

**Use Case**: Post-processing Whisper-generated transcripts

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": true,
  "preserve_sound_events": false,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": false,
  "capitalize": true,
  "fix_all_caps": false,
  "remove_fillers": true,
  "filler_level": 1,
  "segment_sentences": false,
  "merge_short_segments": true,
  "min_segment_length_ms": 1000,
  "max_gap_for_merge_ms": 500,
  "speaker_format": "structured",
  "detect_hallucinations": true,
  "language_specific_rules": true
}
```

**Notes**:
- Whisper already segments well, so less aggressive sentence splitting
- Hallucination detection is important for Whisper output
- Whisper typically has good capitalization, less aggressive fixing

---

### presentation

**Description**: Cleanup for presentation-style content (talks, lectures)

**Use Case**: Conference talks, lectures, educational content where speaker changes and pauses are important

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": false,
  "preserve_sound_events": true,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": true,
  "capitalize": true,
  "fix_all_caps": true,
  "remove_fillers": false,
  "filler_level": 0,
  "segment_sentences": true,
  "merge_short_segments": false,
  "speaker_format": "dialogue",
  "detect_hallucinations": true,
  "language_specific_rules": true
}
```

**Notes**:
- Preserves natural speech patterns including fillers
- Keeps sound events like [APPLAUSE] for context
- Uses dialogue format for clear speaker attribution
- Doesn't merge segments to preserve natural pauses

---

### technical

**Description**: Minimal cleanup for technical content with code, URLs, or specialized terminology

**Use Case**: Technical tutorials, coding streams, developer content

**Configuration**:
```json
{
  "normalize_unicode": false,
  "normalize_whitespace": true,
  "remove_special_tokens": false,
  "preserve_sound_events": true,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": false,
  "capitalize": false,
  "fix_all_caps": false,
  "remove_fillers": true,
  "filler_level": 1,
  "segment_sentences": false,
  "merge_short_segments": true,
  "speaker_format": "structured",
  "detect_hallucinations": true,
  "language_specific_rules": false
}
```

**Notes**:
- Preserves Unicode characters (for code snippets, symbols)
- Minimal capitalization changes (preserves case-sensitive terms)
- Doesn't fix all-caps (may be intentional acronyms)
- Conservative language rules to avoid breaking technical terms

---

### accessibility

**Description**: Optimized for accessibility and screen reader compatibility

**Use Case**: Transcripts intended for users with disabilities using assistive technology

**Configuration**:
```json
{
  "normalize_unicode": true,
  "normalize_whitespace": true,
  "remove_special_tokens": false,
  "preserve_sound_events": true,
  "add_punctuation": true,
  "punctuation_mode": "rule-based",
  "add_internal_punctuation": true,
  "capitalize": true,
  "fix_all_caps": true,
  "remove_fillers": true,
  "filler_level": 2,
  "segment_sentences": true,
  "merge_short_segments": false,
  "speaker_format": "inline",
  "detect_hallucinations": true,
  "language_specific_rules": true
}
```

**Notes**:
- Keeps sound events for context (important for screen readers)
- More internal punctuation for better screen reader pacing
- Inline speaker format for clear attribution
- Doesn't merge to preserve natural speech rhythm

---

## Using Profiles in API Calls

### Method 1: By Profile Name

```bash
# Get cleaned transcript using standard profile
curl -X GET "http://localhost:8000/videos/{video_id}/transcript?format=cleaned&profile=standard"
```

### Method 2: Profile with Overrides

```bash
# Use standard profile but override filler level
curl -X POST "http://localhost:8000/transcripts/{transcript_id}/cleanup" \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "standard",
    "overrides": {
      "filler_level": 3,
      "speaker_format": "dialogue"
    }
  }'
```

### Method 3: Custom Configuration

```bash
# Fully custom configuration
curl -X POST "http://localhost:8000/transcripts/{transcript_id}/cleanup" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "normalize_unicode": true,
      "remove_fillers": true,
      "filler_level": 2,
      "add_punctuation": true,
      "capitalize": true
    }
  }'
```

## Python SDK Examples

```python
from transcript_create_client import TranscriptCreateClient
from transcript_create_client.models import CleanupConfig

client = TranscriptCreateClient(api_key="your_api_key")

# Use predefined profile
transcript = await client.get_transcript(
    video_id="123e4567-e89b-12d3-a456-426614174000",
    format="cleaned",
    profile="standard"
)

# Use profile with overrides
transcript = await client.cleanup_transcript(
    transcript_id="123e4567-e89b-12d3-a456-426614174000",
    profile="aggressive",
    overrides={"filler_level": 2}
)

# Custom configuration
config = CleanupConfig(
    remove_fillers=True,
    filler_level=3,
    add_punctuation=True,
    capitalize=True
)
transcript = await client.cleanup_transcript(
    transcript_id="123e4567-e89b-12d3-a456-426614174000",
    config=config
)
```

## Profile Selection Guide

Use this decision tree to choose the right profile:

1. **Is the content technical (code, URLs, commands)?**
   - Yes → Use `technical` profile
   - No → Continue

2. **Is this for accessibility/screen readers?**
   - Yes → Use `accessibility` profile
   - No → Continue

3. **Is the source YouTube auto-captions?**
   - Yes → Use `youtube_captions` profile
   - No → Continue

4. **Is the source Whisper transcription?**
   - Yes → Use `whisper_output` profile
   - No → Continue

5. **Is this a presentation/lecture?**
   - Yes → Use `presentation` profile
   - No → Continue

6. **Do you want maximum cleanup?**
   - Yes → Use `aggressive` profile
   - No → Use `standard` profile (default)

7. **Need minimal changes?**
   - Yes → Use `minimal` profile

## Creating Custom Profiles

You can define custom profiles in your application configuration:

```python
# app/cleanup_profiles.py

CUSTOM_PROFILES = {
    "my_custom_profile": CleanupConfig(
        normalize_unicode=True,
        remove_fillers=True,
        filler_level=2,
        add_punctuation=True,
        # ... other settings
    )
}
```

Then register them in your API:

```python
# app/routes/transcripts.py

from app.cleanup_profiles import CUSTOM_PROFILES

@router.get("/cleanup/profiles")
async def list_cleanup_profiles():
    """List all available cleanup profiles."""
    return {
        "profiles": list(CLEANUP_PROFILES.keys()) + list(CUSTOM_PROFILES.keys())
    }

@router.get("/cleanup/profiles/{profile_name}")
async def get_cleanup_profile(profile_name: str):
    """Get details of a specific cleanup profile."""
    if profile_name in CLEANUP_PROFILES:
        return CLEANUP_PROFILES[profile_name]
    elif profile_name in CUSTOM_PROFILES:
        return CUSTOM_PROFILES[profile_name]
    else:
        raise HTTPException(status_code=404, detail="Profile not found")
```

## Testing Profiles

To test a profile on sample data, you can use the development/debugging test endpoint (note: this endpoint is for testing purposes and may not be available in production):

```bash
# Use the test endpoint (development/debugging only)
curl -X POST "http://localhost:8000/cleanup/test" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "um hello everyone [MUSIC] welcome to the show",
    "profile": "standard"
  }'
```

Expected response format (for development/debugging):
```json
{
  "input": "um hello everyone [MUSIC] welcome to the show",
  "output": "Hello everyone, welcome to the show.",
  "profile": "standard",
  "transformations": [
    "removed_filler: um",
    "removed_special_token: [MUSIC]",
    "added_capitalization",
    "added_punctuation: ."
  ]
}
```

**Note**: The `/cleanup/test` endpoint shown above is a proposed development/debugging endpoint and is not part of the core API specification. It should be implemented as a convenience tool for testing cleanup transformations during development.

## Performance Considerations

Profile complexity affects processing time:

| Profile | Relative Speed | Memory Usage |
|---------|----------------|--------------|
| minimal | Fastest (1x) | Lowest |
| standard | Fast (1.2x) | Low |
| youtube_captions | Medium (1.5x) | Medium |
| whisper_output | Fast (1.1x) | Low |
| aggressive | Slower (2x) | Medium |
| technical | Fast (1.1x) | Low |
| presentation | Medium (1.3x) | Medium |
| accessibility | Medium (1.4x) | Medium |

**Note**: Model-based punctuation (if enabled) adds significant overhead (~5-10x) but provides better quality.

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-02 | Initial profiles defined |
