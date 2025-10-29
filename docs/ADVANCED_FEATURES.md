# Advanced Transcription Features

This document describes the advanced transcription features added to Transcript Create.

## Features Overview

### 1. Multi-Language Support

Whisper supports 100+ languages with automatic language detection.

**Auto-detection (default):**
```bash
# Leave WHISPER_LANGUAGE empty in .env
WHISPER_LANGUAGE=
```

**Specify language:**
```bash
# Set to specific language code
WHISPER_LANGUAGE=es  # Spanish
WHISPER_LANGUAGE=fr  # French
WHISPER_LANGUAGE=ja  # Japanese
```

**API Usage:**
```json
POST /jobs
{
  "url": "https://www.youtube.com/watch?v=...",
  "quality": {
    "language": "es"
  }
}
```

**Database Storage:**
- `transcripts.detected_language`: Auto-detected language code
- `transcripts.language_probability`: Detection confidence (0-1)
- `transcripts.language`: Final language used (user-specified or detected)

### 2. Quality Presets

Three quality presets optimize for different use cases:

| Preset | Model | Beam Size | Word Timestamps | Use Case |
|--------|-------|-----------|-----------------|----------|
| **fast** | base | 1 | No | Quick preview, low accuracy OK |
| **balanced** | large-v3 | 5 | Yes | Default, good balance |
| **accurate** | large-v3 | 10 | Yes | Maximum accuracy, slower |

**Configuration:**
```bash
# Set default preset in .env
WHISPER_QUALITY_PRESET=balanced
```

**API Usage:**
```json
POST /jobs
{
  "url": "https://www.youtube.com/watch?v=...",
  "quality": {
    "preset": "accurate"
  }
}
```

**Custom overrides:**
```json
POST /jobs
{
  "url": "https://www.youtube.com/watch?v=...",
  "quality": {
    "preset": "balanced",
    "beam_size": 8,
    "temperature": 0.2
  }
}
```

### 3. Custom Vocabulary

Improve accuracy for domain-specific terms, proper nouns, and acronyms.

**Create vocabulary:**
```json
POST /vocabularies
{
  "name": "Tech Terms",
  "terms": [
    {
      "pattern": "kubernetes",
      "replacement": "Kubernetes",
      "case_sensitive": false
    },
    {
      "pattern": "API",
      "replacement": "API",
      "case_sensitive": true
    }
  ],
  "is_global": false
}
```

**Apply to job:**
```json
POST /jobs
{
  "url": "https://www.youtube.com/watch?v=...",
  "vocabulary_ids": ["vocab-uuid-here"]
}
```

**Vocabulary Processing:**
- Applied after transcription and diarization
- Regex-based word boundary matching
- Case-sensitive or insensitive options
- Global vocabularies apply to all jobs
- User-specific vocabularies require authentication

### 4. Word-Level Timestamps

Extract precise timing for individual words (Whisper native feature).

**Enable:**
```bash
WHISPER_WORD_TIMESTAMPS=true
```

**API:**
```json
POST /jobs
{
  "url": "https://www.youtube.com/watch?v=...",
  "quality": {
    "word_timestamps": true
  }
}
```

**Database Storage:**
```json
segments.word_timestamps: [
  {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.98},
  {"word": "world", "start": 0.6, "end": 1.0, "probability": 0.95}
]
```

**Use Cases:**
- Subtitle synchronization
- Karaoke-style highlighting
- Word-level confidence analysis
- Precise clip extraction

### 5. Quality Parameters

Fine-tune transcription quality beyond presets:

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| `beam_size` | 1-10 | 5 | Higher = more accurate, slower |
| `temperature` | 0.0-1.0 | 0.0 | 0 = deterministic, higher = creative |
| `vad_filter` | true/false | false | Voice activity detection |
| `word_timestamps` | true/false | true | Word-level timing |

**Environment:**
```bash
WHISPER_BEAM_SIZE=5
WHISPER_TEMPERATURE=0.0
WHISPER_VAD_FILTER=false
```

**API:**
```json
{
  "quality": {
    "beam_size": 10,
    "temperature": 0.0,
    "vad_filter": true
  }
}
```

## Database Schema

### New Tables

**translations:**
```sql
CREATE TABLE translations (
    id UUID PRIMARY KEY,
    transcript_id UUID REFERENCES transcripts(id),
    target_language TEXT,
    provider TEXT,  -- 'google', 'deepl', 'libretranslate'
    segments JSONB,
    full_text TEXT,
    created_at TIMESTAMPTZ
);
```

**user_vocabularies:**
```sql
CREATE TABLE user_vocabularies (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    name TEXT,
    terms JSONB,  -- [{pattern, replacement, case_sensitive}]
    is_global BOOLEAN,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

### Updated Columns

**transcripts:**
- `detected_language TEXT`: Auto-detected language
- `language_probability REAL`: Detection confidence

**segments:**
- `word_timestamps JSONB`: Word-level timing data

**jobs:**
- `meta JSONB`: Quality settings and vocabulary IDs

## API Endpoints

### Vocabularies

```
GET    /vocabularies          List all vocabularies
POST   /vocabularies          Create vocabulary
GET    /vocabularies/{id}     Get vocabulary details
DELETE /vocabularies/{id}     Delete vocabulary
```

### Jobs (Enhanced)

```
POST   /jobs                  Create job with quality settings
{
  "url": "...",
  "kind": "single",
  "quality": {
    "preset": "balanced",
    "language": "en",
    "beam_size": 5,
    "word_timestamps": true
  },
  "vocabulary_ids": ["uuid1", "uuid2"]
}
```

## Migration

Run the new migration to add tables and columns:

```bash
# Using Alembic
alembic upgrade head

# Or apply directly
psql $DATABASE_URL -f sql/schema.sql
```

## Examples

### High-Quality Spanish Transcription

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=...",
    "kind": "single",
    "quality": {
      "preset": "accurate",
      "language": "es",
      "word_timestamps": true
    }
  }'
```

### Tech Vocabulary Correction

```bash
# Create vocabulary
curl -X POST http://localhost:8000/vocabularies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "DevOps Terms",
    "terms": [
      {"pattern": "kubernetes", "replacement": "Kubernetes"},
      {"pattern": "docker", "replacement": "Docker"},
      {"pattern": "CI/CD", "replacement": "CI/CD", "case_sensitive": true}
    ]
  }'

# Use in job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=...",
    "vocabulary_ids": ["vocab-uuid"]
  }'
```

## Performance Considerations

- **Quality presets:**
  - `fast`: ~2-3x faster than balanced
  - `balanced`: Default, good tradeoff
  - `accurate`: ~1.5-2x slower than balanced

- **Word timestamps:**
  - Adds ~10-20% overhead
  - Increases segment storage by ~30%

- **Custom vocabulary:**
  - Post-processing step, minimal impact
  - Regex matching is fast (<1ms per segment)

## Troubleshooting

### Language detection fails
- Check that audio quality is good
- Ensure speech is present in first chunk
- Try specifying language manually

### Vocabulary not applied
- Verify `ENABLE_CUSTOM_VOCABULARY=true`
- Check vocabulary ID in job metadata
- Ensure patterns use word boundaries

### Word timestamps missing
- Verify `word_timestamps: true` in quality settings
- Check Whisper backend supports it (both do)
- Inspect `segments.word_timestamps` column

## Future Enhancements

Planned features not yet implemented:

- Translation API integration
- Confidence-based filtering
- Audio enhancement pre-processing
- Batch CSV upload
- Advanced export formats (ASS/SSA, TTML)
- LLM-based vocabulary correction
