# Transcript Cleanup Quick Reference

Quick reference for the transcript cleanup module. For complete details, see [TRANSCRIPT_CLEANUP_SPEC.md](TRANSCRIPT_CLEANUP_SPEC.md).

## Quick Start

### Using Default Cleanup

```python
# API Call
GET /videos/{video_id}/transcript?format=cleaned

# Result: Standard cleanup applied (conservative fillers, basic punctuation)
```

### Using a Profile

```python
# API Call
GET /videos/{video_id}/transcript?format=cleaned&profile=aggressive

# Profiles: minimal, standard, aggressive, youtube_captions, whisper_output,
#           presentation, technical, accessibility
```

### Custom Configuration

```python
# API Call
POST /transcripts/{transcript_id}/cleanup

# Body
{
  "config": {
    "remove_fillers": true,
    "filler_level": 2,
    "add_punctuation": true,
    "capitalize": true
  }
}
```

## Configuration Options

### Text Normalization

| Setting | Default | Description |
|---------|---------|-------------|
| `normalize_unicode` | `true` | Apply NFC normalization |
| `normalize_whitespace` | `true` | Fix spacing issues |
| `remove_special_tokens` | `true` | Remove [MUSIC], etc. |
| `preserve_sound_events` | `false` | Keep sound markers |

### Punctuation

| Setting | Default | Description |
|---------|---------|-------------|
| `add_punctuation` | `true` | Add periods, question marks |
| `punctuation_mode` | `"rule-based"` | "none", "rule-based", "model-based" |
| `capitalize` | `true` | Capitalize sentences |
| `fix_all_caps` | `true` | Fix ALL CAPS text |

### De-filler

| Setting | Default | Description |
|---------|---------|-------------|
| `remove_fillers` | `true` | Enable filler removal |
| `filler_level` | `1` | 0=off, 1=conservative, 2=moderate, 3=aggressive |

**Filler Levels**:
- **Level 0**: No removal
- **Level 1**: Remove `um`, `uh`, `er` only
- **Level 2**: Add `you know`, `I mean`, stutters
- **Level 3**: Add `like`, `sort of`, `kind of`

### Segmentation

| Setting | Default | Description |
|---------|---------|-------------|
| `segment_sentences` | `true` | Split on sentence boundaries |
| `merge_short_segments` | `true` | Merge close segments |
| `min_segment_length_ms` | `1000` | Min segment duration |
| `max_gap_for_merge_ms` | `500` | Max gap to merge |
| `speaker_format` | `"structured"` | "inline", "dialogue", "structured" |

### Advanced

| Setting | Default | Description |
|---------|---------|-------------|
| `detect_hallucinations` | `true` | Mark repetitive segments |
| `language_specific_rules` | `true` | Use language-aware rules |

## Profiles at a Glance

| Profile | Fillers | Punctuation | Segmentation | Use Case |
|---------|---------|-------------|--------------|----------|
| **minimal** | None | None | None | Preserve original |
| **standard** | Level 1 | Rule-based | Yes | General purpose (default) |
| **aggressive** | Level 3 | Rule-based + internal | Yes | Maximum cleanup |
| **youtube_captions** | Level 2 | Rule-based | Yes | YouTube auto-captions |
| **whisper_output** | Level 1 | Rule-based | Merge only | Whisper transcripts |
| **presentation** | None | Rule-based + internal | Yes | Talks, lectures |
| **technical** | Level 1 | Minimal | Merge only | Code, technical content |
| **accessibility** | Level 2 | Rule-based + internal | No merge | Screen readers |

## Example Transformations

### Basic Cleanup (Standard Profile)

```
Input:  "[MUSIC] um hello everyone uh welcome to the show"
Output: "Hello everyone, welcome to the show."
```

### Question Detection

```
Input:  "what time is it"
Output: "What time is it?"
```

### Filler Removal

```
# Level 1
Input:  "um hello uh world"
Output: "Hello world."

# Level 2
Input:  "I I I think you know it's good"
Output: "I think it's good."

# Level 3
Input:  "so like I think it's kind of good"
Output: "I think it's good."
```

### Multi-Speaker

```
Input:
[
  {"speaker": "SPEAKER_00", "text": "um hello everyone", "start_ms": 0, "end_ms": 1500},
  {"speaker": "SPEAKER_00", "text": "welcome", "start_ms": 1500, "end_ms": 3000},
  {"speaker": "SPEAKER_01", "text": "thanks", "start_ms": 3500, "end_ms": 5000}
]

Output (dialogue format):
Speaker 1: Hello everyone, welcome.

Speaker 2: Thanks.
```

## Environment Variables

Add to `.env`:

```bash
# Enable cleanup
CLEANUP_ENABLED=true

# Text normalization
CLEANUP_NORMALIZE_UNICODE=true
CLEANUP_NORMALIZE_WHITESPACE=true
CLEANUP_REMOVE_SPECIAL_TOKENS=true

# Punctuation
CLEANUP_PUNCTUATION_MODE=rule-based
CLEANUP_ADD_SENTENCE_PUNCTUATION=true
CLEANUP_CAPITALIZE_SENTENCES=true

# De-filler
CLEANUP_REMOVE_FILLERS=true
CLEANUP_FILLER_LEVEL=1

# Segmentation
CLEANUP_SEGMENT_BY_SENTENCES=true
CLEANUP_MERGE_SHORT_SEGMENTS=true
CLEANUP_SPEAKER_FORMAT=structured

# Advanced
CLEANUP_DETECT_HALLUCINATIONS=true
```

## API Endpoints

### Get Transcript with Cleanup

```http
GET /videos/{video_id}/transcript?format=cleaned&profile=standard
```

**Query Parameters**:
- `format`: `raw`, `cleaned`, or `formatted`
- `profile`: Profile name (optional)

**Response**:
```json
{
  "video_id": "uuid",
  "segments": [
    {
      "start_ms": 1000,
      "end_ms": 3500,
      "text_raw": "um hello everyone",
      "text_cleaned": "Hello everyone.",
      "speaker_label": "Speaker 1",
      "sentence_boundary": true
    }
  ],
  "cleanup_config": {...},
  "stats": {
    "fillers_removed": 1,
    "punctuation_added": 1
  }
}
```

### Apply Custom Cleanup

```http
POST /transcripts/{transcript_id}/cleanup
Content-Type: application/json

{
  "config": {
    "remove_fillers": true,
    "filler_level": 3,
    "add_punctuation": true
  }
}
```

### List Profiles

```http
GET /cleanup/profiles
```

**Response**:
```json
{
  "profiles": [
    "minimal",
    "standard",
    "aggressive",
    "youtube_captions",
    "whisper_output",
    "presentation",
    "technical",
    "accessibility"
  ]
}
```

### Get Profile Details

```http
GET /cleanup/profiles/{profile_name}
```

## Python SDK Example

```python
from transcript_create_client import TranscriptCreateClient
from transcript_create_client.models import CleanupConfig

client = TranscriptCreateClient(api_key="your_api_key")

# Use predefined profile
transcript = await client.get_transcript(
    video_id="video-uuid",
    format="cleaned",
    profile="standard"
)

# Custom configuration
config = CleanupConfig(
    remove_fillers=True,
    filler_level=3,
    add_punctuation=True,
    capitalize=True
)

transcript = await client.cleanup_transcript(
    transcript_id="transcript-uuid",
    config=config
)
```

## Common Patterns

### Conservative Cleanup (Preserve Most Content)

```python
{
  "remove_fillers": true,
  "filler_level": 1,
  "add_punctuation": true,
  "capitalize": true,
  "segment_sentences": false
}
```

### Maximum Readability

```python
{
  "remove_fillers": true,
  "filler_level": 3,
  "add_punctuation": true,
  "add_internal_punctuation": true,
  "capitalize": true,
  "fix_all_caps": true,
  "segment_sentences": true,
  "speaker_format": "dialogue"
}
```

### Technical Content

```python
{
  "normalize_unicode": false,
  "remove_fillers": false,
  "add_punctuation": true,
  "capitalize": false,
  "fix_all_caps": false,
  "segment_sentences": false
}
```

## Troubleshooting

### Problem: Too Much Cleaned

**Solution**: Use lower filler level or `minimal` profile

```python
# Instead of
{"filler_level": 3}

# Use
{"filler_level": 1}
# or
profile="minimal"
```

### Problem: Not Enough Punctuation

**Solution**: Enable internal punctuation

```python
{
  "add_punctuation": true,
  "add_internal_punctuation": true
}
```

### Problem: Wrong Speaker Format

**Solution**: Change `speaker_format`

```python
# For plain text output with names
{"speaker_format": "dialogue"}

# For API/JSON with structure
{"speaker_format": "structured"}

# For inline markers
{"speaker_format": "inline"}
```

### Problem: Technical Terms Changed

**Solution**: Use `technical` profile or disable capitalization fixes

```python
profile="technical"
# or
{
  "fix_all_caps": false,
  "normalize_unicode": false,
  "language_specific_rules": false
}
```

### Problem: Segments Too Long/Short

**Solution**: Adjust segmentation thresholds

```python
# For shorter segments
{
  "min_segment_length_ms": 500,
  "max_gap_for_merge_ms": 300
}

# For longer segments
{
  "min_segment_length_ms": 2000,
  "max_gap_for_merge_ms": 1000
}
```

## Performance Tips

1. **Use Caching**: Run optional database migration for faster repeated access
2. **Use Profiles**: Predefined profiles are faster than custom configs
3. **Batch Processing**: Process multiple transcripts in background jobs
4. **Choose Right Level**: Higher filler levels = more processing time

**Typical Performance**:
- 1000 segments: ~300-500ms (standard profile)
- 10,000 segments: ~3-5s (standard profile)
- Cached results: <100ms API response

## Testing

### Test with Sample Text

```bash
curl -X POST http://localhost:8000/cleanup/test \
  -H "Content-Type: application/json" \
  -d '{
    "text": "um hello everyone [MUSIC] welcome to the show",
    "profile": "standard"
  }'
```

**Response**:
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

## Related Documentation

- **Complete Spec**: [TRANSCRIPT_CLEANUP_SPEC.md](TRANSCRIPT_CLEANUP_SPEC.md)
- **Profiles Guide**: [CLEANUP_PROFILES.md](CLEANUP_PROFILES.md)
- **Examples & Tests**: [CLEANUP_EXAMPLES.md](CLEANUP_EXAMPLES.md)
- **Implementation Summary**: [IMPLEMENTATION_SUMMARY_CLEANUP.md](IMPLEMENTATION_SUMMARY_CLEANUP.md)

## Support

For issues or questions:
- Check examples in `CLEANUP_EXAMPLES.md`
- Review profile descriptions in `CLEANUP_PROFILES.md`
- See full spec in `TRANSCRIPT_CLEANUP_SPEC.md`
- Report bugs: [GitHub Issues](https://github.com/subculture-collective/transcript-create/issues)

---

**Last Updated**: 2025-11-02
