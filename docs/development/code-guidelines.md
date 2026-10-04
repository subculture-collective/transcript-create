# Code Guidelines

This document outlines coding standards, patterns, and best practices for contributing to Transcript Create.

## Table of Contents

- [General Principles](#general-principles)
- [Python Style Guide](#python-style-guide)
- [Naming Conventions](#naming-conventions)
- [Error Handling](#error-handling)
- [Testing Requirements](#testing-requirements)
- [Documentation Expectations](#documentation-expectations)
- [Security Guidelines](#security-guidelines)

## General Principles

### Code Quality

- **Clarity over cleverness**: Write code that's easy to understand
- **Consistency**: Follow existing patterns in the codebase
- **DRY (Don't Repeat Yourself)**: Extract common logic into reusable functions
- **YAGNI (You Aren't Gonna Need It)**: Don't add features or abstractions prematurely
- **Test your code**: Write tests that verify your changes work correctly

### Performance

- **Optimize when necessary**: Profile before optimizing
- **Async when beneficial**: Use async/await for I/O-bound operations
- **Database efficiency**: Use appropriate indexes, batch operations, avoid N+1 queries
- **Minimize dependencies**: Only add dependencies that provide significant value

### Maintainability

- **Keep functions small**: Each function should do one thing well
- **Limit nesting**: Max 3 levels of indentation
- **Meaningful variable names**: Prefer `user_email` over `ue`
- **Comment when needed**: Explain "why", not "what"

## Python Style Guide

### PEP 8 Compliance

We follow [PEP 8](https://pep8.org/) with the following specifics:

```python
# Line length: 120 characters (configured in pyproject.toml)
# Indentation: 4 spaces (never tabs)
# String quotes: Double quotes " preferred (configurable)
```

### Type Hints

**Always use type hints** for function signatures:

```python
# Good
def get_video_by_id(video_id: int) -> Optional[Video]:
    """Fetch a video by its ID."""
    return db.query(Video).filter(Video.id == video_id).first()

# Bad - missing type hints
def get_video_by_id(video_id):
    return db.query(Video).filter(Video.id == video_id).first()
```

**Use modern type syntax** (Python 3.10+):

```python
from typing import Optional, Union, Any

# Good - Python 3.10+ syntax
def process_video(video_id: int | None = None) -> dict[str, Any]:
    pass

# Also acceptable - backwards compatible
def process_video(video_id: Optional[int] = None) -> dict:
    pass
```

### Imports

**Order and style**:

```python
# 1. Standard library imports
import os
import sys
from datetime import datetime
from pathlib import Path

# 2. Third-party imports
import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# 3. Local application imports
from app.crud import get_video
from app.db import get_db
from app.settings import settings

# Tools: isort automatically organizes imports
```

### Function Definitions

**Docstrings** for public functions:

```python
def transcribe_chunk(
    audio_path: Path,
    model,
    start_offset: float = 0.0
) -> list[dict]:
    """
    Transcribe an audio chunk using Whisper.

    Args:
        audio_path: Path to the audio file
        model: Loaded Whisper model instance
        start_offset: Time offset in seconds to add to timestamps

    Returns:
        List of segment dictionaries with text, start, end, and confidence

    Raises:
        RuntimeError: If transcription fails
        FileNotFoundError: If audio file doesn't exist
    """
    # Implementation...
```

**Keep functions focused**:

```python
# Good - single responsibility
def download_audio(video_url: str) -> Path:
    """Download audio from YouTube."""
    # Download logic only
    pass

def transcode_audio(input_path: Path, output_path: Path) -> None:
    """Convert audio to 16kHz mono WAV."""
    # Transcoding logic only
    pass

# Bad - doing too much
def download_and_process_audio(video_url: str) -> Path:
    # Download, transcode, chunk, everything...
    pass
```

### Error Handling

**Use specific exceptions**:

```python
# Good - specific exceptions
def get_video_or_404(video_id: int) -> Video:
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")
    return video

# Bad - generic exceptions
def get_video(video_id: int) -> Video:
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise Exception("Not found")
    return video
```

**Context managers** for resource cleanup:

```python
# Good
with open(audio_path, "rb") as f:
    data = f.read()

with engine.begin() as conn:
    result = conn.execute(text("SELECT * FROM videos"))

# Bad
f = open(audio_path, "rb")
data = f.read()
f.close()  # May not execute if exception occurs
```

### Database Access

**Use parameterized queries**:

```python
# Good - parameterized
query = text("SELECT * FROM videos WHERE youtube_id = :youtube_id")
result = conn.execute(query, {"youtube_id": youtube_id})

# Bad - SQL injection risk
query = f"SELECT * FROM videos WHERE youtube_id = '{youtube_id}'"
result = conn.execute(text(query))
```

**Use transactions**:

```python
# Good - explicit transaction
with engine.begin() as conn:
    conn.execute(text("UPDATE videos SET state = 'processing' WHERE id = :id"), {"id": video_id})
    conn.execute(text("INSERT INTO transcripts ..."))
    # Automatically commits on success, rolls back on exception

# Bad - autocommit mode with multiple writes
conn.execute(text("UPDATE videos ..."))
conn.execute(text("INSERT INTO transcripts ..."))  # May fail, leaving inconsistent state
```

### Configuration

**Use settings, not hardcoded values**:

```python
# Good - configurable
from app.settings import settings

chunk_seconds = settings.CHUNK_SECONDS
whisper_model = settings.WHISPER_MODEL

# Bad - hardcoded
chunk_seconds = 900
whisper_model = "large-v3"
```

### Logging

**Use structured logging**:

```python
import logging

logger = logging.getLogger(__name__)

# Good - structured with context
logger.info("Starting transcription", extra={
    "video_id": video_id,
    "model": model_name,
    "duration_seconds": duration
})

# Also good - f-string for readability
logger.info(f"Transcribing video {video_id} with {model_name}")

# Bad - concatenation
logger.info("Transcribing video " + str(video_id) + " with " + model_name)
```

## Naming Conventions

### Python

```python
# Variables and functions: snake_case
video_id = 123
def process_video(video_id: int) -> None:
    pass

# Classes: PascalCase
class VideoProcessor:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_CHUNK_SECONDS = 900
DEFAULT_MODEL = "large-v3"

# Private methods: _leading_underscore
def _internal_helper():
    pass

# File names: snake_case.py
# video_processor.py, audio_utils.py
```

### Database

```sql
-- Tables: snake_case, plural
CREATE TABLE videos (
  id SERIAL PRIMARY KEY,
  youtube_id TEXT NOT NULL
);

-- Columns: snake_case
CREATE TABLE transcripts (
  video_id INTEGER REFERENCES videos(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes: idx_table_column
CREATE INDEX idx_videos_youtube_id ON videos(youtube_id);

-- Enums: snake_case, singular
CREATE TYPE job_state AS ENUM ('pending', 'processing', 'completed', 'failed');
```

## Error Handling

### Python

**Be specific about exceptions**:

```python
# Good
try:
    audio_path = download_audio(url)
except HTTPError as e:
    logger.error(f"Failed to download audio: {e}")
    raise
except IOError as e:
    logger.error(f"Failed to save audio: {e}")
    raise

# Bad
try:
    audio_path = download_audio(url)
except Exception as e:
    pass  # Swallows all errors
```

**Provide context in exceptions**:

```python
# Good
if not audio_path.exists():
    raise FileNotFoundError(f"Audio file not found: {audio_path}")

# Bad
if not audio_path.exists():
    raise FileNotFoundError()
```

## Testing Requirements

### Test Coverage

- **Aim for 70%+ coverage** for backend code
- **Test critical paths** thoroughly
- **Test edge cases** and error conditions

### Backend Tests (pytest)

```python
# tests/test_video_processing.py

def test_download_audio_success(tmp_path):
    """Test successful audio download."""
    url = "https://youtube.com/watch?v=test"
    audio_path = download_audio(url, output_dir=tmp_path)
    
    assert audio_path.exists()
    assert audio_path.suffix == ".m4a"

def test_download_audio_invalid_url():
    """Test audio download with invalid URL."""
    with pytest.raises(ValueError, match="Invalid YouTube URL"):
        download_audio("not-a-url")

def test_transcode_audio_creates_wav(tmp_path):
    """Test audio transcoding to WAV format."""
    input_path = tmp_path / "input.m4a"
    output_path = tmp_path / "output.wav"
    
    # Setup: create test audio file
    create_test_audio(input_path)
    
    transcode_audio(input_path, output_path)
    
    assert output_path.exists()
    # Verify WAV format properties
    assert get_audio_format(output_path) == "wav"
    assert get_sample_rate(output_path) == 16000
```

## Documentation Expectations

### Code Comments

**When to comment**:
- Complex algorithms or business logic
- Non-obvious design decisions
- Workarounds for bugs or limitations
- Public API functions

**When NOT to comment**:
- Obvious code (`i++  # increment i`)
- Variable declarations that are self-explanatory
- Restating what the code does

```python
# Good - explains why
def calculate_chunk_size(duration: float) -> int:
    """
    Calculate optimal chunk size for audio processing.
    
    We use 15-minute chunks to balance memory usage with processing
    efficiency. Smaller chunks increase overhead, larger chunks risk
    OOM errors with large models.
    """
    return min(duration, settings.CHUNK_SECONDS)

# Bad - restates the obvious
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    # Add a and b
    result = a + b  # Store result
    return result  # Return the result
```

### README and Documentation

- Keep README up to date with setup instructions
- Document API endpoints in docstrings (OpenAPI auto-generates from these)
- Add migration guides for breaking changes
- Update CHANGELOG.md for user-facing changes

## Security Guidelines

### Input Validation

```python
# Good - validate and sanitize
from pydantic import BaseModel, validator

class JobCreate(BaseModel):
    url: str
    kind: Literal["single", "channel"]
    
    @validator("url")
    def validate_youtube_url(cls, v):
        if not v.startswith("https://youtube.com") and not v.startswith("https://www.youtube.com"):
            raise ValueError("Must be a valid YouTube URL")
        return v
```

### SQL Injection Prevention

```python
# Good - parameterized queries
query = text("SELECT * FROM videos WHERE youtube_id = :youtube_id")
result = conn.execute(query, {"youtube_id": youtube_id})

# Bad - string concatenation
query = f"SELECT * FROM videos WHERE youtube_id = '{youtube_id}'"
```

### Secrets Management

```python
# Good - environment variables
from app.settings import settings
api_key = settings.YOUTUBE_API_KEY

# Bad - hardcoded
api_key = "hardcoded-secret"  # Never commit secrets!
```

### Authentication

```python
# Good - require authentication
from app.auth import get_current_user

@router.get("/admin/users")
async def list_users(user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return get_all_users()
```

## Tools and Automation

### Linting and Formatting

Run before committing:

```bash
# Python
ruff check app/ worker/ scripts/
black app/ worker/ scripts/
isort app/ worker/ scripts/
mypy app/ worker/
```

### Pre-commit Hooks

Install once:

```bash
pre-commit install
```

Runs automatically on `git commit`:
- Linting (ruff)
- Formatting (black)
- Import sorting (isort)
- Secret detection (gitleaks)
- Trailing whitespace removal

## Questions?

- Check [CONTRIBUTING.md](../../CONTRIBUTING.md) for workflow details
- Review existing code for examples
- Ask in issues or discussions
- Refer to official docs: [PEP 8](https://pep8.org/)

Happy coding! 🚀
