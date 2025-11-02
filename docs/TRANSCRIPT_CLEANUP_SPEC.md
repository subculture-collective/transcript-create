# Transcript Cleanup, Punctuation, and Segmentation Module

**Version**: 1.0  
**Status**: Draft  
**Created**: 2025-11-02  
**Author**: GitHub Copilot

## Table of Contents

1. [Overview](#overview)
2. [Goals and Scope](#goals-and-scope)
3. [Text Normalization](#text-normalization)
4. [Punctuation and Capitalization](#punctuation-and-capitalization)
5. [De-filler Rules](#de-filler-rules)
6. [Segmentation Strategy](#segmentation-strategy)
7. [Configuration and API Surface](#configuration-and-api-surface)
8. [Implementation Approaches](#implementation-approaches)
9. [Examples and Edge Cases](#examples-and-edge-cases)
10. [Testing Strategy](#testing-strategy)
11. [Future Enhancements](#future-enhancements)

---

## Overview

This specification defines a post-processing module for transcript cleanup that works with both YouTube auto-captions and Whisper-generated transcripts. The module transforms raw transcription output into readable, properly formatted text suitable for human consumption and downstream processing.

### Problem Statement

Raw transcripts from both YouTube and Whisper often contain:
- Inconsistent or missing punctuation
- No sentence boundaries or improper segmentation
- Filler words and disfluencies (um, uh, like, you know)
- Inconsistent capitalization
- Special tokens (e.g., `[MUSIC]`, `[APPLAUSE]`)
- Excessive whitespace and Unicode normalization issues
- Run-on segments that span multiple sentences

### Design Principles

1. **Start Simple**: Begin with deterministic, rule-based approaches
2. **Preserve Accuracy**: Never change the semantic meaning of content
3. **Configurable**: Allow users to control cleanup aggressiveness
4. **Non-Destructive**: Always preserve raw transcripts; cleanup creates new representations
5. **Idempotent**: Running cleanup multiple times produces same result
6. **Language-Aware**: Support multi-language content appropriately

---

## Goals and Scope

### In Scope

- **Text normalization**: Whitespace, Unicode, special characters
- **Punctuation restoration**: Add/fix periods, commas, question marks, exclamation points
- **Capitalization**: Sentence-initial and proper nouns
- **De-filler rules**: Remove or minimize common filler words
- **Segmentation**: Break transcripts into sentence/phrase boundaries
- **Speaker formatting**: Preserve and enhance speaker labels from diarization
- **Configuration system**: Flexible settings for different use cases
- **API extensions**: New endpoints and parameters for accessing cleaned transcripts

### Out of Scope (for v1)

- Grammar correction beyond punctuation
- Spell checking or word correction
- Content summarization
- Translation
- Named entity recognition
- Emotion/sentiment labeling
- Real-time streaming cleanup (batch only)

---

## Text Normalization

### Whitespace Normalization

**Purpose**: Standardize spacing for consistent processing and display

**Rules**:
1. Replace all Unicode whitespace variants (nbsp, thin space, etc.) with ASCII space (U+0020)
2. Collapse multiple consecutive spaces into single space
3. Remove leading and trailing whitespace from segments
4. Normalize line endings to LF (`\n`)
5. Remove zero-width characters (zero-width space, zero-width joiner, etc.)

**Implementation**:
```python
import re
import unicodedata

def normalize_whitespace(text: str) -> str:
    """Normalize all whitespace variants to single ASCII space."""
    # Replace Unicode whitespace with ASCII space
    text = re.sub(r'[\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000\uFEFF]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text)
    # Remove zero-width characters
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.strip()
```

### Unicode Normalization

**Purpose**: Standardize character representations for consistent matching and display

**Rules**:
1. Apply NFC (Canonical Composition) normalization by default
2. Convert lookalike characters to ASCII equivalents when appropriate
3. Preserve emoji and necessary Unicode characters

**Implementation**:
```python
def normalize_unicode(text: str) -> str:
    """Apply Unicode NFC normalization."""
    return unicodedata.normalize('NFC', text)
```

### Special Token Handling

**Purpose**: Process or remove non-speech annotations from raw transcripts

**Common Special Tokens**:
- `[MUSIC]`, `[APPLAUSE]`, `[LAUGHTER]`
- `(inaudible)`, `(unintelligible)`
- `♪ music ♪`
- Whisper hallucinations: repetitive phrases, credits, subtitles info

**Rules**:
1. Remove YouTube-style brackets: `[MUSIC]`, `[APPLAUSE]`
2. Remove music notation: `♪` symbols
3. Optionally preserve or remove parenthetical notations
4. Detect and remove Whisper hallucinations (repetitive text at end)

**Configuration Options**:
- `remove_special_tokens`: Boolean (default: `true`)
- `preserve_sound_events`: Boolean (default: `false`) - Keep `[MUSIC]`, `[APPLAUSE]`
- `remove_parentheticals`: Boolean (default: `false`)

**Implementation**:
```python
def remove_special_tokens(text: str, preserve_sound_events: bool = False) -> str:
    """Remove special tokens from transcript."""
    if not preserve_sound_events:
        # Remove common sound event markers
        text = re.sub(r'\[(?:MUSIC|APPLAUSE|LAUGHTER|NOISE)\]', '', text, flags=re.IGNORECASE)
    
    # Remove music notation
    text = re.sub(r'♪+', '', text)
    
    # Remove common Whisper artifacts
    text = re.sub(r'\(.*?Subtitles by.*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(.*?www\..*?\.com.*?\)', '', text, flags=re.IGNORECASE)
    
    return text
```

### Detecting Whisper Hallucinations

**Common Patterns**:
- Repetitive phrases (same sentence repeated 3+ times)
- Credits/attribution appearing at end
- "Thanks for watching" boilerplate
- Timestamp artifacts

**Detection Strategy**:
```python
def detect_hallucination(segments: list) -> list:
    """Detect and mark potential hallucinations in segments."""
    if len(segments) < 3:
        return segments
    
    # Check last few segments for repetition
    last_texts = [s['text'].strip().lower() for s in segments[-5:]]
    if len(last_texts) >= 3:
        if len(set(last_texts[-3:])) == 1:  # Same text 3 times
            # Mark or remove these segments
            for seg in segments[-3:]:
                seg['likely_hallucination'] = True
    
    return segments
```

---

## Punctuation and Capitalization

### Punctuation Restoration

**Purpose**: Add or fix sentence-ending punctuation and internal commas for readability

**Approach Options**:

#### Option 1: Rule-Based (Recommended for v1)

**Advantages**:
- Fast, deterministic
- No model dependencies
- Predictable behavior
- Works offline

**Rules**:
1. Add period to end of segment if missing terminal punctuation
2. Detect questions by interrogative words (who, what, where, when, why, how) → add `?`
3. Detect common comma positions (after introductory words, before conjunctions)
4. Use pause duration from timestamps as comma hint (pause > 0.5s)

**Implementation**:
```python
def add_sentence_punctuation(text: str, is_question: bool = None) -> str:
    """Add terminal punctuation to text."""
    text = text.strip()
    if not text:
        return text
    
    # Check if already has terminal punctuation
    if text[-1] in '.!?':
        return text
    
    # Auto-detect questions
    if is_question is None:
        is_question = bool(re.match(
            r'^(who|what|where|when|why|how|is|are|can|could|would|should|do|does|did)\b',
            text.lower()
        ))
    
    return text + ('?' if is_question else '.')

def add_internal_punctuation(text: str, pause_ms: int = None) -> str:
    """Add commas based on linguistic rules and optional pause duration."""
    # After introductory words
    text = re.sub(r'^(however|furthermore|moreover|additionally|meanwhile|therefore)\s+',
                  r'\1, ', text, flags=re.IGNORECASE)
    
    # Before coordinating conjunctions with clauses
    text = re.sub(r'\s+(and|but|or|so|yet)\s+',
                  r', \1 ', text)
    
    # If pause duration available and significant (>500ms), consider comma
    # This would be integrated with segment merging logic
    
    return text
```

#### Option 2: Model-Based (Future Enhancement)

**Advantages**:
- More accurate punctuation
- Better handling of complex sentences
- Can handle multiple languages with language-specific models

**Disadvantages**:
- Requires model loading (memory + startup time)
- GPU preferred for speed
- Additional dependency
- Less predictable

**Recommended Models** (from Hugging Face research):
- **General Purpose**: Fine-tuned T5 or BERT models for token classification
  - Custom training on YouTube caption data
  - Multi-language support via mT5 models
- **English Specific**: 
  - Community models like `shashank2123/t5-base-fine-tuned-for-Punctuation-Restoration`
  - Token classification models using BERT/RoBERTa

**Implementation Pattern**:
```python
from transformers import pipeline

class PunctuationRestorer:
    def __init__(self, model_name: str = None):
        self.model = None
        if model_name:
            self.model = pipeline("token-classification", model=model_name)
    
    def restore(self, text: str) -> str:
        """Restore punctuation using ML model."""
        if not self.model:
            raise ValueError("Model not loaded")
        
        # Model returns token classifications
        # Post-process to insert punctuation
        # Details depend on specific model output format
        pass
```

**Configuration**:
```python
PUNCTUATION_MODE = "rule-based"  # or "model-based"
PUNCTUATION_MODEL = None  # or model path/name
```

### Capitalization

**Purpose**: Apply proper sentence-initial and proper noun capitalization

**Rules**:
1. Capitalize first letter of each sentence
2. Capitalize after terminal punctuation (. ! ?)
3. Capitalize "I" pronoun
4. Preserve all-caps words (likely acronyms) - but provide option to fix
5. Optionally capitalize known proper nouns (requires dictionary)

**Implementation**:
```python
def capitalize_sentences(text: str) -> str:
    """Capitalize first letter of sentences."""
    # Split on sentence boundaries
    sentences = re.split(r'([.!?]+\s+)', text)
    
    result = []
    for i, part in enumerate(sentences):
        if i % 2 == 0 and part:  # Text part, not separator
            # Capitalize first letter
            part = part[0].upper() + part[1:] if len(part) > 0 else part
        result.append(part)
    
    text = ''.join(result)
    
    # Capitalize standalone "i"
    text = re.sub(r'\bi\b', 'I', text)
    
    return text

def fix_all_caps(text: str, min_length: int = 4) -> bool:
    """Detect if text is inappropriately all-caps."""
    # Ignore short strings (likely acronyms)
    if len(text) < min_length:
        return False
    
    # Count uppercase letters
    upper_count = sum(1 for c in text if c.isupper())
    letter_count = sum(1 for c in text if c.isalpha())
    
    if letter_count == 0:
        return False
    
    # If >80% uppercase, likely needs fixing
    return (upper_count / letter_count) > 0.8
```

---

## De-filler Rules

### Filler Word Removal

**Purpose**: Remove or minimize verbal disfluencies that clutter transcripts

**Common Filler Words** (English):
- `um`, `uh`, `uhm`, `umm`
- `er`, `erm`
- `like` (when used as filler)
- `you know`
- `I mean`
- `sort of`, `kind of`
- Stutters: `I I I think`

**Strategy Levels**:

#### Level 1: Conservative (default)
- Remove only clear non-semantic fillers: `um`, `uh`, `er`
- Preserve words that might be semantic: `like`, `you know`

#### Level 2: Moderate
- Remove Level 1 + obvious filler phrases: `you know`, `I mean`
- Handle stutters: `I I I` → `I`

#### Level 3: Aggressive
- Remove all common fillers including `like`, `sort of`, `kind of`
- Risk: May change meaning in some contexts

**Implementation**:
```python
def remove_fillers(text: str, level: int = 1) -> str:
    """Remove filler words based on aggressiveness level."""
    
    # Level 1: Clear fillers only
    if level >= 1:
        # Remove um, uh, er (with word boundaries)
        text = re.sub(r'\b(um+|uh+m?|er+m?)\b', '', text, flags=re.IGNORECASE)
    
    # Level 2: Moderate - add filler phrases
    if level >= 2:
        text = re.sub(r'\byou know\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bI mean\b', '', text, flags=re.IGNORECASE)
        
        # Handle stutters - repeated words
        text = re.sub(r'\b(\w+)(\s+\1){2,}\b', r'\1', text, flags=re.IGNORECASE)
    
    # Level 3: Aggressive
    if level >= 3:
        text = re.sub(r'\blike\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(sort|kind) of\b', '', text, flags=re.IGNORECASE)
    
    # Clean up extra spaces created by removals
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()
```

**Configuration**:
```python
DE_FILLER_LEVEL = 1  # 0=disabled, 1=conservative, 2=moderate, 3=aggressive
```

### Language-Specific Fillers

**Support for multiple languages**:
- Spanish: `este`, `pues`, `o sea`
- French: `euh`, `ben`, `alors`
- German: `ähm`, `also`

**Implementation Pattern**:
```python
FILLER_PATTERNS = {
    'en': [r'\bum+\b', r'\buh+\b', r'\ber+m?\b', r'\byou know\b'],
    'es': [r'\beste\b', r'\bpues\b', r'\bo sea\b'],
    'fr': [r'\beuh+\b', r'\bben\b', r'\balors\b'],
    'de': [r'\bähm+\b', r'\balso\b'],
}

def remove_fillers_multi(text: str, language: str = 'en', level: int = 1) -> str:
    """Remove language-specific fillers."""
    patterns = FILLER_PATTERNS.get(language, FILLER_PATTERNS['en'])
    
    for pattern in patterns[:level]:  # Use only patterns up to level
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return re.sub(r'\s+', ' ', text).strip()
```

---

## Segmentation Strategy

### Sentence Boundary Detection

**Purpose**: Split run-on segments into natural sentence boundaries for better readability

**Problem**: Whisper often generates segments based on:
- Audio pauses (may not align with sentences)
- Fixed-length windows
- VAD (Voice Activity Detection) segments

This results in segments containing multiple sentences or partial sentences.

**Strategy**:

#### Rule-Based Sentence Splitting (v1)

**Rules**:
1. Split on terminal punctuation followed by capital letter: `. A`, `! S`, `? W`
2. Respect quotation marks - don't split within quotes
3. Handle abbreviations (Dr., Mr., U.S.) - don't split after these
4. Minimum sentence length threshold (e.g., 10 characters)

**Implementation**:
```python
# Common abbreviations that shouldn't trigger splits
ABBREVIATIONS = {'dr', 'mr', 'mrs', 'ms', 'prof', 'sr', 'jr', 
                 'etc', 'vs', 'i.e', 'e.g', 'u.s', 'u.k'}

def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using rule-based approach."""
    # Add space after periods not preceded by abbreviations
    def should_split(match):
        word_before = match.group(1).lower().rstrip('.')
        if word_before in ABBREVIATIONS:
            return match.group(0)  # Don't split
        return match.group(1) + match.group(2) + ' <SPLIT> '
    
    # Mark split points
    text = re.sub(r'(\w+\.)\s+([A-Z])', should_split, text)
    text = re.sub(r'([!?])\s+([A-Z])', r'\1 <SPLIT> \2', text)
    
    # Split and clean
    sentences = [s.strip() for s in text.split('<SPLIT>')]
    sentences = [s for s in sentences if len(s) > 10]  # Min length filter
    
    return sentences
```

#### Timestamp-Aware Segmentation

**Purpose**: Use timing information to inform better segment boundaries

**Strategy**:
1. Merge segments if gap < threshold (e.g., 500ms) AND no sentence boundary
2. Split segments if gap > threshold AND contains multiple sentences
3. Preserve speaker changes as hard boundaries

**Implementation**:
```python
def merge_segments_by_timing(segments: list, max_gap_ms: int = 500) -> list:
    """Merge segments with small gaps that don't have sentence boundaries."""
    if not segments:
        return segments
    
    merged = []
    current = segments[0].copy()
    
    for next_seg in segments[1:]:
        gap_ms = next_seg['start_ms'] - current['end_ms']
        
        # Check for speaker change (hard boundary)
        speaker_change = (current.get('speaker_label') != next_seg.get('speaker_label'))
        
        # Check for sentence boundary
        has_boundary = current['text'].rstrip()[-1] in '.!?' if current['text'] else False
        
        if gap_ms <= max_gap_ms and not speaker_change and not has_boundary:
            # Merge
            current['end_ms'] = next_seg['end_ms']
            current['text'] = current['text'] + ' ' + next_seg['text']
        else:
            # Start new segment
            merged.append(current)
            current = next_seg.copy()
    
    merged.append(current)
    return merged
```

### Speaker-Aware Formatting

**Purpose**: Preserve and enhance speaker labels from diarization

**Format Options**:

#### Option 1: Inline Speaker Labels
```
[Speaker 1] Hello everyone, welcome to the video.
[Speaker 2] Thanks for having me.
[Speaker 1] Let's get started with the topic.
```

#### Option 2: Dialogue Format
```
Speaker 1: Hello everyone, welcome to the video.

Speaker 2: Thanks for having me.

Speaker 1: Let's get started with the topic.
```

#### Option 3: Structured (JSON/API)
```json
{
  "segments": [
    {
      "speaker": "Speaker 1",
      "text": "Hello everyone, welcome to the video.",
      "start_ms": 1000,
      "end_ms": 3500
    }
  ]
}
```

**Implementation**:
```python
def format_with_speakers(segments: list, format: str = 'dialogue') -> str:
    """Format segments with speaker labels."""
    if format == 'inline':
        lines = [f"[{s['speaker_label']}] {s['text']}" for s in segments]
        return '\n'.join(lines)
    
    elif format == 'dialogue':
        lines = []
        current_speaker = None
        for seg in segments:
            speaker = seg.get('speaker_label')
            if speaker != current_speaker:
                if current_speaker is not None:
                    lines.append('')  # Blank line between speakers
                lines.append(f"{speaker}: {seg['text']}")
                current_speaker = speaker
            else:
                # Same speaker continues
                lines.append(seg['text'])
        return '\n\n'.join(lines)
    
    else:  # structured - return list
        return segments
```

### Paragraph Grouping

**Purpose**: Group related sentences into paragraphs for longer transcripts

**Heuristics**:
1. Same speaker → same paragraph (up to max length)
2. Long pause (>2s) → paragraph break
3. Topic change detection (optional, advanced)
4. Maximum paragraph length (e.g., 5 sentences or 500 chars)

**Implementation**:
```python
def group_into_paragraphs(segments: list, max_sentences: int = 5) -> list:
    """Group segments into paragraphs."""
    paragraphs = []
    current_para = []
    sentence_count = 0
    current_speaker = None
    
    for seg in segments:
        speaker = seg.get('speaker_label')
        
        # Start new paragraph on speaker change
        if speaker != current_speaker and current_para:
            paragraphs.append(current_para)
            current_para = []
            sentence_count = 0
        
        current_para.append(seg)
        sentence_count += 1
        current_speaker = speaker
        
        # Start new paragraph after max sentences
        if sentence_count >= max_sentences:
            paragraphs.append(current_para)
            current_para = []
            sentence_count = 0
    
    if current_para:
        paragraphs.append(current_para)
    
    return paragraphs
```

---

## Configuration and API Surface

### Configuration Schema

**Settings Location**: `app/settings.py`

```python
# Cleanup module settings
CLEANUP_ENABLED: bool = True

# Text normalization
NORMALIZE_UNICODE: bool = True
NORMALIZE_WHITESPACE: bool = True
REMOVE_SPECIAL_TOKENS: bool = True
PRESERVE_SOUND_EVENTS: bool = False

# Punctuation and capitalization
PUNCTUATION_MODE: Literal["none", "rule-based", "model-based"] = "rule-based"
PUNCTUATION_MODEL: Optional[str] = None  # HF model name if model-based
ADD_SENTENCE_PUNCTUATION: bool = True
ADD_INTERNAL_PUNCTUATION: bool = False
CAPITALIZE_SENTENCES: bool = True
FIX_ALL_CAPS: bool = True

# De-filler
DE_FILLER_LEVEL: int = 1  # 0=disabled, 1=conservative, 2=moderate, 3=aggressive

# Segmentation
SEGMENT_BY_SENTENCES: bool = True
MERGE_SHORT_SEGMENTS: bool = True
MIN_SEGMENT_LENGTH_MS: int = 1000
MAX_GAP_FOR_MERGE_MS: int = 500
SPEAKER_FORMAT: Literal["inline", "dialogue", "structured"] = "structured"

# Advanced
DETECT_HALLUCINATIONS: bool = True
LANGUAGE_SPECIFIC_RULES: bool = True
```

### API Extensions

#### New Query Parameters

**GET /videos/{video_id}/transcript**

Add optional query parameters for cleanup:

```python
@router.get("/videos/{video_id}/transcript")
async def get_transcript(
    video_id: uuid.UUID,
    format: Literal["raw", "cleaned", "formatted"] = "raw",
    cleanup_config: Optional[CleanupConfig] = None,
):
    """
    Get transcript with optional cleanup.
    
    Parameters:
    - format: 
        - "raw": Original transcript, no processing
        - "cleaned": Apply text normalization, punctuation, de-filler
        - "formatted": Apply cleaning + segmentation + speaker formatting
    - cleanup_config: Optional override of default cleanup settings
    """
    pass
```

**New Schema**:

```python
class CleanupConfig(BaseModel):
    """Configuration for transcript cleanup."""
    
    # Normalization
    normalize_unicode: bool = True
    normalize_whitespace: bool = True
    remove_special_tokens: bool = True
    
    # Punctuation
    add_punctuation: bool = True
    punctuation_mode: Literal["rule-based", "model-based"] = "rule-based"
    capitalize: bool = True
    
    # De-filler
    remove_fillers: bool = True
    filler_level: int = Field(1, ge=0, le=3)
    
    # Segmentation
    segment_sentences: bool = True
    merge_short_segments: bool = True
    speaker_format: Literal["inline", "dialogue", "structured"] = "structured"


class CleanedSegment(BaseModel):
    """Segment with cleaned text."""
    
    start_ms: int
    end_ms: int
    text_raw: str  # Original text
    text_cleaned: str  # After cleanup
    speaker_label: Optional[str] = None
    sentence_boundary: bool = False  # True if this ends a sentence


class CleanedTranscriptResponse(BaseModel):
    """Cleaned transcript response."""
    
    video_id: uuid.UUID
    segments: List[CleanedSegment]
    cleanup_config: CleanupConfig
    metadata: Dict[str, Any]  # Stats about cleanup (fillers removed, etc.)
```

#### New Endpoints

**POST /transcripts/{transcript_id}/cleanup**

```python
@router.post("/transcripts/{transcript_id}/cleanup")
async def cleanup_transcript(
    transcript_id: uuid.UUID,
    config: CleanupConfig,
) -> CleanedTranscriptResponse:
    """
    Apply cleanup to a transcript and return result.
    Does not modify original transcript in database.
    """
    pass
```

**POST /transcripts/{transcript_id}/cleanup/save**

```python
@router.post("/transcripts/{transcript_id}/cleanup/save")
async def save_cleaned_transcript(
    transcript_id: uuid.UUID,
    config: CleanupConfig,
) -> uuid.UUID:
    """
    Apply cleanup and save as a new transcript variant.
    Returns new transcript_id for the cleaned version.
    """
    pass
```

### Database Schema Extensions

**Option 1: Add Cleanup Metadata Column**

```sql
-- Add to existing transcripts table
ALTER TABLE transcripts ADD COLUMN cleanup_config JSONB;
ALTER TABLE transcripts ADD COLUMN is_cleaned BOOLEAN DEFAULT false;

-- Add to segments table
ALTER TABLE segments ADD COLUMN text_cleaned TEXT;
ALTER TABLE segments ADD COLUMN cleanup_applied BOOLEAN DEFAULT false;
```

**Option 2: Separate Cleaned Transcripts Table**

```sql
CREATE TABLE cleaned_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript_id UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    cleanup_config JSONB NOT NULL,
    full_text_cleaned TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cleaned_segments (
    id BIGSERIAL PRIMARY KEY,
    cleaned_transcript_id UUID NOT NULL REFERENCES cleaned_transcripts(id) ON DELETE CASCADE,
    segment_id BIGINT REFERENCES segments(id),
    text_cleaned TEXT NOT NULL,
    start_ms INT NOT NULL,
    end_ms INT NOT NULL,
    speaker_label TEXT
);
```

**Recommendation**: Use Option 1 for simplicity. Add columns to existing tables with default values for backward compatibility.

---

## Implementation Approaches

### Approach 1: In-Memory Processing (Recommended for v1)

**Description**: Apply cleanup on-the-fly when transcript is requested via API

**Advantages**:
- No database schema changes required
- Easy to iterate on cleanup logic
- No storage overhead for cleaned versions
- Always uses latest cleanup rules

**Disadvantages**:
- Processing overhead on each request
- May be slower for large transcripts
- No caching of cleaned results

**Implementation**:
```python
# In app/routes/videos.py

@router.get("/videos/{video_id}/transcript")
async def get_transcript(
    video_id: uuid.UUID,
    format: Literal["raw", "cleaned", "formatted"] = "raw",
    db: Session = Depends(get_db),
):
    # Fetch raw segments
    segments = fetch_segments(db, video_id)
    
    if format == "raw":
        return {"segments": segments}
    
    # Apply cleanup
    from worker.cleanup import apply_cleanup
    
    config = CleanupConfig()  # Use defaults or from request
    cleaned_segments = apply_cleanup(segments, config)
    
    if format == "cleaned":
        return {"segments": cleaned_segments}
    
    # Format with speakers, paragraphs
    formatted = format_transcript(cleaned_segments, config)
    return {"transcript": formatted}
```

**Worker Module Structure**:
```
worker/
  cleanup/
    __init__.py
    normalizer.py      # Text normalization functions
    punctuation.py     # Punctuation restoration
    filler.py          # De-filler logic
    segmentation.py    # Sentence boundary detection
    formatter.py       # Output formatting
```

### Approach 2: Background Processing with Caching

**Description**: Run cleanup as a background job, cache results in database

**Advantages**:
- Fast API responses (return cached results)
- Can run expensive ML models without blocking
- Results are versioned and persistent

**Disadvantages**:
- More complex implementation
- Storage overhead
- Need to handle cache invalidation when cleanup logic changes

**Implementation Sketch**:
```python
# Worker adds cleanup step to pipeline
def process_video(video_id):
    # ... existing transcription ...
    
    # Apply default cleanup
    cleaned_segments = apply_cleanup(segments, DEFAULT_CLEANUP_CONFIG)
    
    # Save to database
    save_cleaned_transcript(video_id, cleaned_segments, DEFAULT_CLEANUP_CONFIG)
```

### Approach 3: Hybrid (Recommended for Production)

**Description**: Cache common cleanup configs, compute custom configs on-demand

**Strategy**:
1. Worker applies default cleanup and caches in `text_cleaned` column
2. API returns cached result for default config (fast path)
3. API computes custom cleanup on-demand (slow path, with caching layer)

**Implementation**:
```python
@router.get("/videos/{video_id}/transcript")
async def get_transcript(
    video_id: uuid.UUID,
    format: Literal["raw", "cleaned", "formatted"] = "raw",
    cleanup_config: Optional[CleanupConfig] = None,
    cache: Cache = Depends(get_cache),
    db: Session = Depends(get_db),
):
    if format == "raw":
        return fetch_raw_segments(db, video_id)
    
    # Check if using default config
    if cleanup_config is None or cleanup_config == DEFAULT_CLEANUP_CONFIG:
        # Fast path - return pre-computed cleaned text
        return fetch_cleaned_segments(db, video_id)
    
    # Custom config - check cache
    cache_key = f"cleaned:{video_id}:{hash(cleanup_config)}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # Compute and cache
    segments = fetch_raw_segments(db, video_id)
    cleaned = apply_cleanup(segments, cleanup_config)
    cache.set(cache_key, cleaned, ttl=3600)  # 1 hour
    
    return cleaned
```

### Trade-offs Summary

| Aspect | In-Memory | Background | Hybrid |
|--------|-----------|------------|--------|
| **Implementation Complexity** | Low | High | Medium |
| **API Response Time** | Variable | Fast | Fast (default) / Variable (custom) |
| **Storage Requirements** | None | High | Medium |
| **Flexibility** | High | Medium | High |
| **Maintenance** | Easy | Complex | Medium |
| **Recommended For** | MVP, prototyping | High-volume production | Production with flexibility |

**Recommendation for v1**: Start with **In-Memory Processing** approach. This allows rapid iteration on cleanup logic without database migrations. Add caching layer in v2 if performance becomes an issue.

---

## Examples and Edge Cases

### Example 1: Basic YouTube Transcript Cleanup

**Input (Raw YouTube Auto-Caption)**:
```
[Music]
so today we're gonna talk about
um
the new features and uh
you know how to use them
[Applause]
this is really exciting
```

**Output (Cleaned, Level 1)**:
```
So today we're going to talk about the new features and how to use them. This is really exciting.
```

**Transformations Applied**:
- Removed `[Music]` and `[Applause]`
- Removed fillers: `um`, `uh`, `you know`
- Fixed: `gonna` → `going to`
- Added capitalization and punctuation
- Merged segments into sentences

### Example 2: Whisper Output with Hallucination

**Input (Raw Whisper)**:
```
Welcome to my channel.
If you enjoyed this video, please like and subscribe.
Thanks for watching!
Thanks for watching!
Thanks for watching!
```

**Output (Cleaned with Hallucination Detection)**:
```
Welcome to my channel. If you enjoyed this video, please like and subscribe. Thanks for watching!
```

**Transformations Applied**:
- Detected repetition (last 3 segments identical)
- Removed hallucinated repetitions

### Example 3: Multi-Speaker with Diarization

**Input (Raw Segments)**:
```json
[
  {"speaker": "SPEAKER_00", "text": "hello everyone", "start_ms": 0, "end_ms": 1500},
  {"speaker": "SPEAKER_00", "text": "welcome to the show", "start_ms": 1500, "end_ms": 3000},
  {"speaker": "SPEAKER_01", "text": "thanks for having me", "start_ms": 3500, "end_ms": 5000},
  {"speaker": "SPEAKER_01", "text": "excited to be here", "start_ms": 5000, "end_ms": 6500}
]
```

**Output (Formatted Dialogue)**:
```
Speaker 1: Hello everyone, welcome to the show.

Speaker 2: Thanks for having me, excited to be here.
```

**Transformations Applied**:
- Renamed `SPEAKER_00` → `Speaker 1`, `SPEAKER_01` → `Speaker 2`
- Merged consecutive segments from same speaker
- Added proper capitalization and punctuation
- Applied dialogue formatting

### Example 4: All-Caps Transcript

**Input**:
```
HELLO EVERYONE AND WELCOME TO MY CHANNEL TODAY WE'RE GOING TO TALK ABOUT DOCKER
```

**Output**:
```
Hello everyone and welcome to my channel. Today we're going to talk about Docker.
```

**Transformations Applied**:
- Detected inappropriate all-caps
- Converted to sentence case
- Split into sentences
- Preserved "Docker" as proper noun

### Edge Cases

#### Edge Case 1: Abbreviations in Punctuation

**Challenge**: Don't split sentences after abbreviations like "Dr." or "U.S."

**Input**: `Dr. Smith said the U.S. economy is strong.`

**Expected**: Single sentence (no split)

**Handling**: Maintain abbreviation dictionary, check before splitting

#### Edge Case 2: Quoted Speech

**Challenge**: Punctuation inside quotes

**Input**: `He said "what time is it" and left.`

**Expected**: `He said, "What time is it?" and left.`

**Handling**: Quote-aware punctuation rules (advanced)

#### Edge Case 3: Mixed Languages

**Challenge**: Different punctuation rules across languages

**Input**: `Hello! ¿Cómo estás? I'm fine.`

**Expected**: Preserve language-specific punctuation

**Handling**: Language detection per segment, apply appropriate rules

#### Edge Case 4: Technical Content

**Challenge**: Code snippets, URLs, technical terms

**Input**: `Visit github.com slash user slash repo for the code`

**Expected**: Preserve technical content, minimal cleanup

**Handling**: Pattern detection for URLs, code patterns; disable aggressive cleanup

#### Edge Case 5: Empty or Very Short Segments

**Challenge**: Segments with only fillers or very brief

**Input**: `um`, `uh huh`, `yeah`

**Expected**: Handle gracefully, possibly merge or remove

**Handling**: Minimum segment length threshold, merge with adjacent

---

## Testing Strategy

### Unit Tests

**Scope**: Test individual cleanup functions in isolation

**Test Files**:
```
tests/unit/
  test_normalizer.py
  test_punctuation.py
  test_filler.py
  test_segmentation.py
  test_formatter.py
```

**Example Tests**:

```python
# tests/unit/test_normalizer.py

def test_normalize_whitespace():
    input_text = "Hello  world\u00A0test"
    expected = "Hello world test"
    assert normalize_whitespace(input_text) == expected

def test_remove_special_tokens():
    input_text = "[MUSIC] Hello world [APPLAUSE]"
    expected = "Hello world"
    assert remove_special_tokens(input_text) == expected

def test_detect_hallucination():
    segments = [
        {"text": "Hello"},
        {"text": "Thanks for watching"},
        {"text": "Thanks for watching"},
        {"text": "Thanks for watching"},
    ]
    result = detect_hallucination(segments)
    assert result[-1]["likely_hallucination"] == True
```

```python
# tests/unit/test_punctuation.py

def test_add_sentence_punctuation():
    assert add_sentence_punctuation("hello world") == "hello world."
    assert add_sentence_punctuation("what time is it") == "what time is it?"
    assert add_sentence_punctuation("hello world!") == "hello world!"

def test_capitalize_sentences():
    input_text = "hello. world. how are you."
    expected = "Hello. World. How are you."
    assert capitalize_sentences(input_text) == expected
```

```python
# tests/unit/test_filler.py

def test_remove_fillers_level1():
    input_text = "um hello uh world er test"
    expected = "hello world test"
    assert remove_fillers(input_text, level=1) == expected

def test_remove_fillers_level2():
    input_text = "I I I think you know it's good"
    expected = "I think it's good"
    assert remove_fillers(input_text, level=2) == expected
```

### Integration Tests

**Scope**: Test full cleanup pipeline with realistic data

**Test Files**:
```
tests/integration/
  test_cleanup_pipeline.py
  test_cleanup_api.py
```

**Example Tests**:

```python
# tests/integration/test_cleanup_pipeline.py

def test_full_cleanup_youtube_transcript():
    """Test cleanup on realistic YouTube transcript."""
    raw_segments = [
        {"start_ms": 0, "end_ms": 2000, "text": "[Music] um hello everyone"},
        {"start_ms": 2000, "end_ms": 4000, "text": "welcome to the show"},
    ]
    
    config = CleanupConfig(
        remove_fillers=True,
        filler_level=1,
        add_punctuation=True,
    )
    
    result = apply_cleanup(raw_segments, config)
    
    assert len(result) == 1  # Merged into one segment
    assert "[Music]" not in result[0]["text_cleaned"]
    assert "um" not in result[0]["text_cleaned"]
    assert result[0]["text_cleaned"].endswith(".")

def test_cleanup_preserves_speaker_labels():
    """Test that speaker labels are preserved during cleanup."""
    raw_segments = [
        {"speaker_label": "Speaker 1", "text": "hello", "start_ms": 0, "end_ms": 1000},
        {"speaker_label": "Speaker 2", "text": "hi there", "start_ms": 1500, "end_ms": 2500},
    ]
    
    result = apply_cleanup(raw_segments, CleanupConfig())
    
    assert result[0]["speaker_label"] == "Speaker 1"
    assert result[1]["speaker_label"] == "Speaker 2"
```

```python
# tests/integration/test_cleanup_api.py

async def test_get_cleaned_transcript(client, sample_video_id):
    """Test API endpoint for cleaned transcript."""
    response = await client.get(
        f"/videos/{sample_video_id}/transcript?format=cleaned"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "segments" in data
    
    # Verify cleanup was applied
    for segment in data["segments"]:
        assert "text_cleaned" in segment
        # Should have punctuation
        assert segment["text_cleaned"].endswith((".", "!", "?"))

async def test_custom_cleanup_config(client, sample_video_id):
    """Test API with custom cleanup configuration."""
    config = {
        "remove_fillers": True,
        "filler_level": 3,  # Aggressive
        "add_punctuation": True,
    }
    
    response = await client.get(
        f"/videos/{sample_video_id}/transcript?format=cleaned",
        json={"cleanup_config": config}
    )
    
    assert response.status_code == 200
```

### End-to-End Tests

**Scope**: Test cleanup as part of full transcription workflow

```python
# tests/e2e/test_cleanup_workflow.py

async def test_transcription_with_automatic_cleanup(client):
    """Test that cleanup is automatically applied after transcription."""
    # Create job
    job_response = await client.post("/jobs", json={
        "url": "https://youtube.com/watch?v=test",
        "kind": "single",
    })
    job_id = job_response.json()["id"]
    
    # Wait for completion (mock or use test video)
    # ...
    
    # Get transcript - should have cleaned version available
    response = await client.get(f"/videos/{video_id}/transcript?format=cleaned")
    
    assert response.status_code == 200
    assert "segments" in response.json()
```

### Regression Tests

**Purpose**: Ensure cleanup doesn't break existing functionality

**Test Cases**:
1. API backward compatibility - `format=raw` still works
2. Database schema backward compatibility
3. Export functionality (SRT, VTT, PDF) works with cleaned text
4. Search indexing includes cleaned text

### Performance Tests

**Metrics to Track**:
- Cleanup processing time per 1000 segments
- Memory usage during cleanup
- API response time with cleanup enabled

**Benchmarks**:
```python
import time

def benchmark_cleanup():
    """Benchmark cleanup performance."""
    # Generate large test dataset
    segments = generate_test_segments(count=10000)
    
    start = time.time()
    result = apply_cleanup(segments, CleanupConfig())
    elapsed = time.time() - start
    
    print(f"Processed {len(segments)} segments in {elapsed:.2f}s")
    print(f"Rate: {len(segments)/elapsed:.0f} segments/sec")
    
    # Assert performance target
    assert elapsed < 5.0  # Should process 10k segments in <5s
```

---

## Future Enhancements

### Phase 2: Model-Based Punctuation

**Goal**: Improve punctuation accuracy using fine-tuned transformer models

**Tasks**:
1. Collect training data from high-quality transcripts
2. Fine-tune T5 or BERT model for punctuation restoration
3. Integrate model inference into cleanup pipeline
4. Add model serving infrastructure (GPU-accelerated inference)
5. Benchmark against rule-based approach

**Success Metrics**:
- Punctuation accuracy >95% on test set
- <50ms inference time per segment on GPU
- User preference testing shows improvement

### Phase 3: Advanced Segmentation

**Goal**: Improve segment boundaries using ML-based approaches

**Approaches**:
- Sentence boundary detection models
- Topic modeling for paragraph breaks
- Intent detection for conversation flow

### Phase 4: Multi-Language Support

**Goal**: Extend cleanup to support 10+ languages

**Tasks**:
1. Build language-specific filler word dictionaries
2. Adapt punctuation rules for language-specific conventions
3. Train or fine-tune multi-language punctuation models
4. Add language detection to auto-select appropriate rules

### Phase 5: Semantic Improvements

**Goal**: Make transcripts more readable through semantic understanding

**Features**:
- Named entity recognition → proper capitalization
- Grammar correction beyond punctuation
- Disfluency repair (fix false starts, self-corrections)
- Summarization for long transcripts

### Phase 6: Real-Time Cleanup

**Goal**: Apply cleanup to streaming transcripts in real-time

**Challenges**:
- Partial sentence handling
- Low-latency processing
- Incremental updates to cleaned text

**Use Cases**:
- Live streaming transcription
- Real-time captions with cleanup

---

## Appendix

### A. Filler Word Dictionary

**English**:
```python
ENGLISH_FILLERS = {
    'level_1': ['um', 'uh', 'uhm', 'umm', 'er', 'erm', 'ah', 'ahh'],
    'level_2': ['you know', 'i mean', 'like', 'well', 'actually', 'basically'],
    'level_3': ['sort of', 'kind of', 'you see', 'right', 'okay', 'so'],
}
```

**Spanish**:
```python
SPANISH_FILLERS = {
    'level_1': ['eh', 'este', 'pues', 'mm'],
    'level_2': ['o sea', 'bueno', 'entonces', 'claro'],
    'level_3': ['como', 'digamos', 'algo así'],
}
```

### B. Abbreviation Dictionary

```python
ABBREVIATIONS = {
    'en': ['dr', 'mr', 'mrs', 'ms', 'prof', 'sr', 'jr', 'phd', 'md',
           'etc', 'vs', 'i.e', 'e.g', 'et al', 'inc', 'corp', 'ltd',
           'u.s', 'u.k', 'u.n', 'ft', 'st', 'ave', 'blvd'],
}
```

### C. Benchmark Dataset

For testing and benchmarking, create a curated dataset:

**Structure**:
```
tests/fixtures/transcripts/
  youtube_auto_captions/
    sample_01_raw.json
    sample_01_expected_cleaned.json
  whisper_output/
    sample_02_raw.json
    sample_02_expected_cleaned.json
  edge_cases/
    all_caps.json
    heavy_fillers.json
    multi_speaker.json
    hallucination.json
```

**Sample Format**:
```json
{
  "name": "YouTube Auto-Caption Sample 1",
  "description": "Tech talk with moderate fillers",
  "raw_segments": [...],
  "expected_cleaned": {
    "level_1": [...],
    "level_2": [...],
    "level_3": [...]
  }
}
```

### D. Configuration Profiles

**Predefined cleanup profiles for common use cases**:

```python
CLEANUP_PROFILES = {
    'minimal': CleanupConfig(
        remove_fillers=False,
        add_punctuation=False,
        normalize_whitespace=True,
    ),
    'standard': CleanupConfig(
        remove_fillers=True,
        filler_level=1,
        add_punctuation=True,
        capitalize=True,
    ),
    'aggressive': CleanupConfig(
        remove_fillers=True,
        filler_level=3,
        add_punctuation=True,
        capitalize=True,
        segment_sentences=True,
    ),
    'youtube_to_whisper': CleanupConfig(
        # Optimized for cleaning YouTube auto-captions
        remove_special_tokens=True,
        remove_fillers=True,
        filler_level=2,
        add_punctuation=True,
    ),
}
```

**API Usage**:
```python
# Use predefined profile
GET /videos/{id}/transcript?format=cleaned&profile=standard

# Or custom config
POST /videos/{id}/transcript/cleanup
{
  "profile": "aggressive",
  "overrides": {
    "filler_level": 2
  }
}
```

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-02 | GitHub Copilot | Initial draft specification |

---

## Acceptance Criteria Checklist

- [x] Defined text normalization (whitespace, Unicode, special tokens)
- [x] Defined sentence punctuation strategy (rule-based + optional model)
- [x] Defined de-filler rules with multiple aggressiveness levels
- [x] Defined capitalization rules
- [x] Defined segmentation strategy (sentence boundaries, timing-aware)
- [x] Defined per-speaker formatting options
- [x] Defined configuration flags and API surface
- [x] Defined implementation approaches with trade-offs
- [x] Included concrete examples for each transformation type
- [x] Documented edge cases and handling strategies
- [x] Proposed testing strategy (unit, integration, e2e)
- [x] Outlined future enhancements
- [x] Provided appendices with supporting data

---

**End of Specification**
