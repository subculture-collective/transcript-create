# Advanced Search Features

This document describes the advanced search capabilities implemented in the transcript-create API.

## Overview

The advanced search features provide powerful filtering, analytics, and export capabilities to enhance the search experience for users and administrators.

## Features

### 1. Advanced Filters

Search results can be filtered using multiple criteria:

#### Date Range Filtering
Filter videos by upload date:
```bash
GET /search?q=python&date_from=2024-01-01&date_to=2024-12-31
```

#### Duration Filtering
Filter by video length (in seconds):
```bash
# Short videos (under 5 minutes)
GET /search?q=tutorial&max_duration=300

# Long videos (over 20 minutes)
GET /search?q=lecture&min_duration=1200

# Medium videos (5-20 minutes)
GET /search?q=demo&min_duration=300&max_duration=1200
```

#### Channel Filtering
Filter by channel name (case-insensitive, partial match):
```bash
GET /search?q=python&channel=TechChannel
```

#### Language Filtering
Filter by language code:
```bash
GET /search?q=machine+learning&language=en
```

#### Speaker Diarization Filtering
Filter videos that have speaker labels:
```bash
GET /search?q=interview&has_speaker_labels=true
```

### 2. Sort Options

Results can be sorted by multiple criteria:

- **relevance** (default) - Best matching results first
- **date_desc** - Newest videos first
- **date_asc** - Oldest videos first
- **duration_desc** - Longest videos first
- **duration_asc** - Shortest videos first

Example:
```bash
GET /search?q=python&sort_by=date_desc
```

### 3. Query Time Tracking

All search responses now include query execution time:

```json
{
  "hits": [...],
  "total": 42,
  "query_time_ms": 156
}
```

### 4. Search Suggestions

Autocomplete functionality based on previous searches:

#### Get Suggestions
```bash
GET /search/suggestions?q=artif&limit=10
```

Response:
```json
{
  "suggestions": [
    {
      "term": "artificial intelligence",
      "frequency": 150
    },
    {
      "term": "artifact",
      "frequency": 12
    }
  ]
}
```

Suggestions are:
- Case-insensitive
- Prefix-matched
- Ordered by frequency and recency
- Automatically updated with each search

### 5. Search History

#### User Search History
View your recent searches:
```bash
GET /search/history?limit=20
```

Response:
```json
{
  "items": [
    {
      "query": "machine learning",
      "filters": {
        "language": "en",
        "min_duration": 300
      },
      "result_count": 42,
      "created_at": "2024-10-26T10:30:00Z"
    }
  ]
}
```

#### Popular Searches
See globally popular search terms:
```bash
GET /search/popular?limit=20
```

Response:
```json
{
  "suggestions": [
    {
      "term": "python",
      "frequency": 523
    },
    {
      "term": "javascript",
      "frequency": 412
    }
  ]
}
```

### 6. Search Analytics (Admin Only)

Comprehensive analytics dashboard for administrators:

```bash
GET /admin/search/analytics?days=30
```

Response:
```json
{
  "popular_terms": [
    {
      "term": "python",
      "frequency": 523,
      "last_used": "2024-10-26T10:30:00Z"
    }
  ],
  "zero_result_searches": [
    {
      "query": "obscure topic",
      "count": 5
    }
  ],
  "search_volume": [
    {
      "date": "2024-10-25",
      "count": 142
    }
  ],
  "avg_results_per_query": 28.5,
  "total_searches": 1523
}
```

**Metrics Provided:**
- **Popular Terms** - Most frequently searched terms
- **Zero-Result Searches** - Queries that returned no results (useful for improving indexing)
- **Search Volume** - Daily search counts over time
- **Average Results** - Mean number of results per query
- **Total Searches** - Total search count in the period

### 7. Export Search Results

Export search results to CSV or JSON format:

#### CSV Export
```bash
GET /search/export?q=python&format=csv&limit=500
```

Returns a CSV file with columns:
- segment_id
- video_id
- youtube_id
- title
- start_ms
- end_ms
- text

#### JSON Export
```bash
GET /search/export?q=python&format=json&limit=500
```

Response:
```json
{
  "query": "python",
  "source": "native",
  "results": [
    {
      "segment_id": 12345,
      "video_id": "uuid",
      "youtube_id": "abc123",
      "title": "Python Tutorial",
      "start_ms": 45000,
      "end_ms": 48500,
      "text": "This is a <em>python</em> tutorial..."
    }
  ],
  "count": 42
}
```

**Export Features:**
- Supports all search filters
- Higher limit (up to 1000 results)
- Includes video metadata
- Ready for analysis in spreadsheets or scripts

## Database Schema

### New Tables

#### search_suggestions
Stores search terms for autocomplete:
```sql
CREATE TABLE search_suggestions (
    id BIGSERIAL PRIMARY KEY,
    term TEXT NOT NULL,
    frequency INT NOT NULL DEFAULT 1,
    last_used TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### user_searches
Tracks user search history:
```sql
CREATE TABLE user_searches (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    filters JSONB DEFAULT '{}'::jsonb,
    result_count INT,
    query_time_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Enhanced Tables

#### videos
New filter columns added:
- `uploaded_at` - Video upload date
- `channel_name` - YouTube channel name
- `language` - Language code
- `category` - Video category

## Implementation Details

### Performance Considerations

1. **Indexes**: All filter columns have indexes for fast queries
2. **Query Time**: Tracked in milliseconds for performance monitoring
3. **Pagination**: Supports offset-based pagination for large result sets
4. **Retry Logic**: Database queries use exponential backoff for transient errors

### Privacy & Security

1. **User History**: Per-user search history only visible to the user
2. **Admin Analytics**: Analytics dashboard restricted to admin users
3. **Rate Limiting**: Search quota enforcement for free plan users
4. **Input Validation**: All inputs validated and sanitized

### Future Enhancements

Planned but not yet implemented:

- **Semantic Search**: Vector embeddings with pgvector for meaning-based search
- **Query Expansion**: Automatic synonym expansion
- **Spelling Correction**: "Did you mean?" suggestions
- **Caching**: Redis layer for frequently searched terms
- **Advanced Syntax**: Boolean operators, phrase search, field-specific queries
- **KWIC (Keyword In Context) View**: Enhanced display with configurable context window

## Migration

To apply the database changes:

```bash
# Using Alembic (recommended)
alembic upgrade head

# Or for fresh installations
psql $DATABASE_URL -f sql/schema.sql
```

The migration (`alembic/versions/20251026_0227_94e8fe9e40fa_add_search_enhancements_tables.py`) adds:
- New tables for suggestions and history
- New columns on videos table
- Indexes for performance

## Examples

### Complete Search with All Filters

```bash
GET /search?q=machine+learning \
    &source=native \
    &date_from=2024-01-01 \
    &date_to=2024-12-31 \
    &min_duration=300 \
    &max_duration=1800 \
    &channel=TechEdu \
    &language=en \
    &has_speaker_labels=true \
    &sort_by=relevance \
    &limit=50 \
    &offset=0
```

### Export with Filters

```bash
GET /search/export?q=python+tutorial \
    &format=csv \
    &min_duration=300 \
    &language=en \
    &sort_by=date_desc \
    &limit=1000
```

### Analytics Dashboard Query

```bash
GET /admin/search/analytics?days=90
```

## API Reference

All endpoints are documented in the interactive OpenAPI specification, accessible at `/docs` when the API server is running (if enabled in your deployment).

### Search Endpoints

- `GET /search` - Main search with filters
- `GET /search/suggestions` - Autocomplete suggestions
- `GET /search/history` - User's search history
- `GET /search/popular` - Popular global searches
- `GET /search/export` - Export results
- `GET /admin/search/analytics` - Analytics dashboard (admin only)

## Support

For issues or questions about advanced search features, please:
1. Check the API documentation at `/docs`
2. Review this document
3. Open an issue on GitHub
